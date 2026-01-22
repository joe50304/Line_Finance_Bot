import os
import requests
import pandas as pd
from datetime import datetime
import pytz  # 用來處理時區
import yfinance as yf
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, JoinEvent, ImageSendMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, ButtonComponent,
    MessageAction, SeparatorComponent
)
from cachetools import cached, TTLCache

app = Flask(__name__)

# --- 設定區 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
TARGET_ID = os.environ.get('MY_USER_ID', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 支援的幣別代碼清單 ---
VALID_CURRENCIES = [
    "USD", "HKD", "GBP", "AUD", "CAD", "SGD", "CHF", "JPY", "ZAR", "SEK", "NZD", 
    "THB", "PHP", "IDR", "EUR", "KRW", "VND", "MYR", "CNY", "INR", "DKK", "MOP", 
    "MXN", "TRY"
]

# --- 1. 問候語與基本工具 ---
def get_greeting():
    try:
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        hour = now.hour
        if 5 <= hour < 12: return "早上好 🌞"
        elif 12 <= hour < 18: return "下午好 🍱"
        elif 18 <= hour < 24: return "晚安 🌙"
        else: return "凌晨好 🌞"
    except:
        return "你好 🤖"

# --- 2. 爬蟲：比率網 (FindRate) ---
# 設定快取: 300秒 (5分鐘)
rate_cache = TTLCache(maxsize=30, ttl=300)

@cached(rate_cache)
def get_taiwan_bank_rates(currency_code="HKD"):
    """
    從比率網 (FindRate) 抓取台灣各家銀行的「現鈔賣出」匯率
    """
    try:
        url = f"https://www.findrate.tw/{currency_code}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' 
        
        dfs = pd.read_html(response.text)
        
        # 鎖定匯率表格 (通常是 dfs[1])
        target_df = None
        if len(dfs) >= 2:
            target_df = dfs[1]
        else:
            for df in dfs:
                if len(df.columns) > 5:
                    target_df = df
                    break
        
        if target_df is None:
            return f"找不到 {currency_code} 的匯率表格，可能該網站未提供。"

        # 準備輸出文字報告
        result_text = f"🏆 {currency_code} 現鈔賣出匯率前 5 名:\n"
        result_text += "(⬇️ 數字越低越好 | 更新時間)\n"
        result_text += "----------------\n"
        
        bank_rates = []
        
        for i in range(len(target_df)):
            try:
                row = target_df.iloc[i]
                # 欄位對應: 0=銀行名稱, 2=現鈔賣出 (這是您指定且驗證過的欄位)
                bank_name = str(row[0]).strip()
                cash_selling = str(row[2]).strip()
                update_time = str(row[5]).strip()
                
                # 過濾標題與無效資料
                if bank_name in ["銀行名稱", "銀行", "幣別"]: continue
                if cash_selling == '--': continue

                rate = float(cash_selling)
                if len(bank_name) > 20: continue # 銀行名字太長通常是抓錯了
                if len(cash_selling) > 10: continue
                bank_rates.append({
                    "bank": bank_name,
                    "rate": rate,
                    "time": update_time
                })
            except:
                continue

        # 排序：由低到高 (賣出價越低越划算)
        bank_rates.sort(key=lambda x: x['rate'])
        
        # 取前 5 名
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            return f"雖然有 {currency_code} 頁面，但今日無銀行提供「現鈔」賣出報價。"

        for i, item in enumerate(top_5_banks, 1):
            if i == 1: icon = "🥇"
            elif i == 2: icon = "🥈"
            elif i == 3: icon = "🥉"
            else: icon = f" {i}."
            result_text += f"{icon} {item['bank']} ({item['time']}): {item['rate']}\n"
            
        return result_text
        
    except Exception as e:
        return f"查詢失敗: {str(e)}"

# --- 3. API：Yahoo Finance (國際匯率) ---
def get_forex_info(currency_code):
    """
    取得外幣對台幣的國際即時行情 (用於顯示紅綠漲跌)
    """
    try:
        symbol = f"{currency_code}TWD=X"
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        
        if not hasattr(info, 'last_price') or info.last_price is None:
            return None

        current_price = info.last_price
        prev_close = info.previous_close
        
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        return {
            "currency": currency_code,
            "price": current_price,
            "change": change,
            "change_percent": change_percent
        }
    except Exception as e:
        print(f"Forex Info Error: {e}")
        return None

# --- 4. 圖表產生器 ---
def generate_forex_chart_url_yf(currency_code, period="1d", interval="15m"):
    """
    產生匯率走勢圖，包含錯誤處理與自動降級
    """
    try:
        symbol = f"{currency_code}TWD=X"
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        # Fallback: 如果 1d 沒資料 (例如週末)，嘗試抓 5d
        if data.empty and period == '1d':
            print(f"{currency_code} 1d data empty, trying 5d...")
            period = '5d'
            interval = '60m'
            data = ticker.history(period=period, interval=interval)

        if data.empty:
            return None
            
        dates = []
        prices = []
        
        # 格式化 X 軸日期
        for index, row in data.iterrows():
            if period == '1d':
                dt_str = index.strftime('%H:%M')
            elif period == '5d':
                dt_str = index.strftime('%m/%d %H')
            else:
                dt_str = index.strftime('%Y-%m-%d')
                
            dates.append(dt_str)
            prices.append(row['Close'])

        # QuickChart 設定
        chart_config = {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [{
                    "label": f"{currency_code}/TWD ({period})",
                    "data": prices,
                    "borderColor": "#1DB446",
                    "backgroundColor": "rgba(29, 180, 70, 0.1)",
                    "fill": True,
                    "pointRadius": 0,
                    "borderWidth": 2,
                    "lineTension": 0.1
                }]
            },
            "options": {
                "title": {"display": True, "text": f"{currency_code} 匯率走勢 ({period})"},
                "legend": {"display": False},
                "scales": {
                    "yAxes": [{"ticks": {"beginAtZero": False}}],
                    "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 6}}] 
                }
            }
        }
        
        url = "https://quickchart.io/chart/create"
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 600,
            "backgroundColor": "white",
            "version": "2.9.4"
        }
        
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            return response.json().get('url')
        else:
            return None
            
    except Exception as e:
        print(f"Chart Error: {e}")
        return None

# --- 5. Flex Message 產生器 ---
def generate_currency_flex_message(forex_data, bank_report_text):
    """
    產生匯率儀表板 (Yahoo 報價 + FindRate 最佳銀行)
    """
    c_code = forex_data['currency']
    price = forex_data['price']
    change = forex_data['change']
    percent = forex_data['change_percent']
    
    # 顏色：紅漲綠跌
    if change > 0:
        color = "#eb4e3d"; sign = "+"
    elif change < 0:
        color = "#27ba46"; sign = ""
    else:
        color = "#333333"; sign = ""

    # 解析最佳銀行 (從比率網的文字報告中提取)
    best_bank_info = "暫無現鈔賣出報價" # 預設值，避免顯示"查詢中"
    try:
        # 只要文字報告中有 🥇，就抓那一整行
        if "🥇" in bank_report_text:
            for line in bank_report_text.split('\n'):
                if "🥇" in line:
                    best_bank_info = line.replace("🥇", "").strip()
                    break
    except:
        pass

    return FlexSendMessage(
        alt_text=f"{c_code} 匯率快報",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    # 標題
                    TextComponent(text=f"{c_code}/TWD 匯率", weight='bold', size='xl', color='#555555'),
                    TextComponent(text="台灣時間即時行情 (Yahoo)", size='xxs', color='#aaaaaa'),
                    
                    # 國際匯率大字
                    BoxComponent(
                        layout='baseline',
                        margin='md',
                        contents=[
                            TextComponent(text=f"{price:.4f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{change:.4f} ({sign}{percent:.2f}%)", size='xs', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    
                    # 最佳銀行 (比率網資料)
                    TextComponent(text="🇹🇼 台灣最佳現鈔賣出 (銀行):", size='xs', color='#aaaaaa', margin='lg'),
                    # 這裡顯示從比率網抓到的第一名
                    TextComponent(text=best_bank_info, weight='bold', size='md', color='#eb4e3d', margin='sm'),
                    
                    # 走勢圖按鈕
                    SeparatorComponent(margin='lg'),
                    TextComponent(text="歷史走勢圖:", size='xs', color='#aaaaaa', margin='md'),
                    BoxComponent(
                        layout='horizontal',
                        margin='sm',
                        spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1日走勢', text=f'{c_code} 1D')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='5日走勢', text=f'{c_code} 5D'))
                        ]
                    ),
                    BoxComponent(
                        layout='horizontal',
                        margin='sm',
                        spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1月走勢', text=f'{c_code} 1M')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1年走勢', text=f'{c_code} 1Y'))
                        ]
                    ),
                    # 完整列表連結
                    ButtonComponent(style='link', height='sm', action=MessageAction(label='查看完整銀行比價', text=f'{c_code} 列表'))
                ]
            )
        )
    )

# --- 6. 台股相關功能 (維持原樣，簡化顯示) ---
def get_stock_info(symbol):
    # (此處省略部分詳細邏輯以節省篇幅，請保留您原本的 get_stock_info 與 get_valid_stock_obj 函式)
    # 為了完整性，這裡提供一個精簡版接口，請確保您原本的台股邏輯還在
    # 如果您需要完整的台股代碼，請將之前的 get_stock_info 貼回來
    # 這裡假設您會保留原本的台股功能
    pass 

# 為了讓程式能跑，我這裡補上台股的必要函式，您可以直接用這一段
def get_valid_stock_obj(symbol):
    def fetch(t):
        try: s = yf.Ticker(t); return s, s.fast_info
        except: return None, None
    for suffix in [".TW", ".TWO"]:
        s, i = fetch(symbol + suffix)
        if i and hasattr(i, 'last_price') and i.last_price: return s, i, suffix
    return None, None, None

def get_stock_info(symbol):
    try:
        stock, info, suffix = get_valid_stock_obj(symbol)
        if not stock: return None
        return {
            "symbol": symbol, "name": symbol, 
            "price": info.last_price, "change": info.last_price - info.previous_close,
            "change_percent": (info.last_price - info.previous_close)/info.previous_close*100,
            "limit_up": info.previous_close*1.1, "limit_down": info.previous_close*0.9,
            "volume": info.last_volume, "high": info.day_high, "low": info.day_low,
            "type": "上櫃" if suffix == ".TWO" else "上市"
        }
    except: return None

def generate_stock_flex_message(data):
    # 台股 Flex Message (簡化版)
    color = "#eb4e3d" if data['change'] > 0 else "#27ba46" if data['change'] < 0 else "#333333"
    return FlexSendMessage(
        alt_text=f"{data['symbol']} 股價",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{data['symbol']}", weight='bold', size='xl'),
                    TextComponent(text=f"{data['price']:.2f}", size='3xl', color=color, weight='bold'),
                    TextComponent(text=f"{data['change']:.2f} ({data['change_percent']:.2f}%)", color=color, size='sm'),
                    ButtonComponent(style='primary', action=MessageAction(label='即時走勢圖', text=f"{data['symbol']} 即時"), margin='md')
                ]
            )
        )
    )

def generate_help_message():
    return FlexSendMessage(
        alt_text="功能選單",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text="🤖 金融助手", weight='bold', size='xl', color='#1DB446'),
                    SeparatorComponent(margin='md'),
                    BoxComponent(
                        layout='horizontal', spacing='sm', margin='md',
                        contents=[
                            ButtonComponent(style='primary', action=MessageAction(label='🇺🇸 USD', text='USD')),
                            ButtonComponent(style='primary', action=MessageAction(label='🇯🇵 JPY', text='JPY')),
                            ButtonComponent(style='primary', action=MessageAction(label='🇭🇰 HKD', text='HKD'))
                        ]
                    ),
                    ButtonComponent(style='link', action=MessageAction(label='查詢 ID', text='ID'))
                ]
            )
        )
    )

def generate_kline_chart_url(symbol, period="1d", interval="5m", title_suffix=""):
    # (保留您原本的台股圖表邏輯)
    return generate_forex_chart_url_yf(symbol.replace('.TW','').replace('.TWO',''), period, interval) # 簡易替代，請保留原本完整版

# --- 7. 主要路由 ---
@app.route("/", methods=['GET'])
def home(): return "Alive", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return 'OK'

@app.route("/push_report", methods=['GET'])
def push_report():
    if not TARGET_ID: return "No Target ID", 500
    try:
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=f"{get_greeting()}！\n{get_taiwan_bank_rates('HKD')}"))
        return "Sent", 200
    except Exception as e: return str(e), 500

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.upper().strip()
    
    # ID 查詢
    if msg in ['ID', '我的ID']:
        tid = event.source.group_id if event.source.type == 'group' else event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID: {tid}"))
        return

    # 功能選單
    if msg in ['HELP', 'MENU', '選單']:
        line_bot_api.reply_message(event.reply_token, generate_help_message())
        return

    # 1. 匯率查詢 (儀表板)
    if msg in VALID_CURRENCIES:
        forex_data = get_forex_info(msg)        # 抓 Yahoo
        bank_report = get_taiwan_bank_rates(msg) # 抓 比率網
        
        if forex_data:
            # 有 Yahoo 資料 -> 顯示漂亮儀表板 (內含比率網資料)
            flex_msg = generate_currency_flex_message(forex_data, bank_report)
            line_bot_api.reply_message(event.reply_token, flex_msg)
        else:
            # Yahoo 掛了 -> 直接回傳比率網文字列表
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=bank_report))
        return

    # 2. 匯率完整列表指令
    parts = msg.split()
    if len(parts) == 2 and parts[1] == '列表' and parts[0] in VALID_CURRENCIES:
        report = get_taiwan_bank_rates(parts[0])
        
        # --- 安全防護：檢查長度 ---
        if len(report) > 4000: # 留一點緩衝 (LINE 上限 5000)
            report = report[:4000] + "\n...(內容過長已截斷)"
            
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=report))
        return

    # 3. 匯率走勢圖指令 (支援 USD 1D, USD 5D...)
    if len(parts) == 2 and parts[0] in VALID_CURRENCIES:
        cmd = parts[1]
        chart_url = None
        if cmd == '1D': chart_url = generate_forex_chart_url_yf(parts[0], '1d', '15m')
        elif cmd == '5D': chart_url = generate_forex_chart_url_yf(parts[0], '5d', '60m')
        elif cmd == '1M': chart_url = generate_forex_chart_url_yf(parts[0], '1mo', '1d')
        elif cmd == '1Y': chart_url = generate_forex_chart_url_yf(parts[0], '1y', '1d')
        
        if chart_url:
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=chart_url, preview_image_url=chart_url))
        else:
            # 只有當指令明確是查圖時，才回傳錯誤，避免誤判
            if cmd in ['1D', '5D', '1M', '1Y']:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 暫無該時段走勢數據 (可能為週末或休市)"))
        return

    # 4. 台股代號 (4-6碼)
    if msg.isalnum() and 4 <= len(msg) <= 6:
        stock = get_stock_info(msg)
        if stock:
            line_bot_api.reply_message(event.reply_token, generate_stock_flex_message(stock))
        return

if __name__ == "__main__":
    app.run()