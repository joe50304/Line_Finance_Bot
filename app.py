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
    PostbackAction, MessageAction, SeparatorComponent
)

app = Flask(__name__)

# --- 設定區 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
TARGET_ID = os.environ.get('MY_USER_ID', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 支援的幣別代碼清單 (擴充版) ---
VALID_CURRENCIES = [
    "USD", "HKD", "GBP", "AUD", "CAD", "SGD", "CHF", "JPY", "ZAR", "SEK", "NZD", 
    "THB", "PHP", "IDR", "EUR", "KRW", "VND", "MYR", "CNY", "INR", "DKK", "MOP", 
    "MXN", "TRY"
]

def get_greeting():
    """
    根據台灣時間回傳 早安/午安/晚安
    """
    try:
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        hour = now.hour
        
        if 5 <= hour < 12:
            return "早上好 🌞"
        elif 12 <= hour < 18:
            return "下午好 🍱"
        elif 18 <= hour < 24:
            return "晚安 🌙"
        elif 24 <= hour < 5:
            return "凌晨好 🌞"
        else:
            return "你好 🤖"
    except:
        return "你好 🤖"

def get_taiwan_bank_rates(currency_code="HKD"):
    try:
        url = f"https://www.findrate.tw/{currency_code}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' 
        
        dfs = pd.read_html(response.text)
        
        # 抓取表格邏輯
        target_df = None
        if len(dfs) >= 2:
            target_df = dfs[1]
        else:
            for df in dfs:
                if len(df.columns) > 5:
                    target_df = df
                    break
        
        if target_df is None:
            return f"找不到 {currency_code} 的匯率資料，可能該網站未提供。"

        # 輸出標題
        result_text = f"🏆 {currency_code} 現鈔賣出匯率前 5 名:\n"
        result_text += "(⬇️ 數字越低越好 | 更新時間)\n"
        result_text += "----------------\n"
        
        bank_rates = []
        
        for i in range(len(target_df)):
            try:
                row = target_df.iloc[i]
                bank_name = str(row[0]).strip()
                cash_selling = str(row[2]).strip()
                update_time = str(row[5]).strip()
                
                # 【關鍵修正】
                # 原本: if "銀行" in bank_name: continue  <-- 這行會殺掉 "兆豐銀行"
                # 改為: 只過濾完全等於 "銀行名稱" 或 "銀行" 的標題列
                if bank_name in ["銀行名稱", "銀行", "幣別"]: continue
                
                # 排除無報價的銀行
                if cash_selling == '--': continue

                rate = float(cash_selling)
                bank_rates.append({
                    "bank": bank_name,
                    "rate": rate,
                    "time": update_time
                })
            except:
                continue

        # 排序：由低到高
        bank_rates.sort(key=lambda x: x['rate'])
        
        # 取前 5 名
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            return f"雖然有 {currency_code} 的頁面，但今日無銀行提供「現鈔」賣出報價。"

        for i, item in enumerate(top_5_banks, 1):
            if i == 1: icon = "🥇"
            elif i == 2: icon = "🥈"
            elif i == 3: icon = "🥉"
            else: icon = f" {i}."
            result_text += f"{icon} {item['bank']} ({item['time']}): {item['rate']}\n"
            
        return result_text
        
    except Exception as e:
        return f"查詢失敗: {str(e)}"

def get_historical_data(currency_code="USD"):
    """
    從 historical.findrate.tw 抓取歷史匯率
    回傳 (dates, cash_rates, spot_rates)
    """
    try:
        url = f"https://historical.findrate.tw/his.php?c={currency_code}"
        dfs = pd.read_html(url)
        
        # 尋找包含匯率的表格
        target_df = None
        for df in dfs:
            # 判斷邏輯: 檢查欄位數量 >= 5
            if len(df.columns) >= 5:
                # 寬鬆檢查: 只要第 3 欄 (即期賣出) 或 第 5 欄 (現鈔賣出) 看起來是數字
                # 或者第一欄包含 "日期" (header)
                try:
                    # Check headers
                    if "日期" in str(df.columns):
                        target_df = df
                        break
                        
                    # Check content numeric
                    # Check first few rows
                    for i in range(min(3, len(df))):
                        row = df.iloc[i]
                        # check if col 2 or 4 is float-able
                        try:
                            float(row.iloc[2]) 
                            target_df = df
                            break
                        except:
                            try:
                                float(row.iloc[4])
                                target_df = df
                                break
                            except: pass
                    if target_df is not None:
                        break
                except:
                    continue
        
        if target_df is None:
            return None, None, None

        # 資料前處理
        dates = []
        cash_rates = []
        spot_rates = []
        
        # 只需要最近 30 筆
        recent_data = target_df.head(30).iloc[::-1]
        
        for index, row in recent_data.iterrows():
            try:
                # 假設第一欄是日期，不管欄位名稱
                date = str(row.iloc[0])
                
                # 嘗試抓取 "現鈔賣出" 和 "即期賣出"
                # 因為欄位名稱可能很亂或空白，這裡嘗試用 column name matching
                
                c_rate = None
                s_rate = None
                
                # 尋找 "現鈔賣出" 所在的 column index
                # 如果沒有 Header，可能需要 Hardcode 索引
                # findrate 歷史頁面通常: 日期 | 即期買入 | 即期賣出 | 現鈔買入 | 現鈔賣出
                # 索引: 0 | 1 | 2 | 3 | 4
                
                # 嘗試用位置取值 (比較保險)
                if len(row) >= 5:
                    s_rate_raw = row.iloc[2] # 即期賣出
                    c_rate_raw = row.iloc[4] # 現鈔賣出
                    
                    # 處理 '--' 的情況
                    if str(s_rate_raw).strip() != '--':
                        s_rate = float(s_rate_raw)
                    
                    if str(c_rate_raw).strip() != '--':
                        c_rate = float(c_rate_raw)
                
                # 如果用 DataFrame header 抓得到更好
                if '即期賣出' in row: s_rate = float(row['即期賣出'])
                if '現鈔賣出' in row: c_rate = float(row['現鈔賣出'])

                if date:
                    dates.append(date)
                    cash_rates.append(c_rate) # 可能為 None
                    spot_rates.append(s_rate) # 可能為 None
            except:
                continue
                
        return dates, cash_rates, spot_rates
    except Exception as e:
        print(f"Error fetching history: {e}")
        return None, None, None

def generate_chart_url(dates, cash_rates, spot_rates, currency_code):
    """
    使用 QuickChart.io 產生圖表 URL (雙線圖)
    """
    if not dates:
        return None
        
    datasets = []
    
    # 加入現鈔賣出折線 (如果有資料)
    # 過濾 None 值 (QuickChart/Chart.js 可以處理 null，但最好是連貫的)
    if any(cash_rates):
        datasets.append({
            "label": "現鈔賣出",
            "data": cash_rates,
            "borderColor": "rgb(255, 99, 132)", # 紅色
            "backgroundColor": "rgba(255, 99, 132, 0.5)",
            "fill": False,
        })
        
    # 加入即期賣出折線
    if any(spot_rates):
        datasets.append({
            "label": "即期賣出",
            "data": spot_rates,
            "borderColor": "rgb(54, 162, 235)", # 藍色
            "backgroundColor": "rgba(54, 162, 235, 0.5)",
            "fill": False,
        })

    if not datasets:
        return None

    # QuickChart 設定
    chart_config = {
        "type": "line",
        "data": {
            "labels": dates,
            "datasets": datasets
        },
        "options": {
            "title": {
                "display": True,
                "text": f"{currency_code}/TWD 近期匯率走勢"
            },
            "interaction": {
                "mode": 'index',
                "intersect": False,
            },
            "scales": {
                # 確保 Y 軸不會從 0 開始，而是根據數據自動調整 (讓起伏更明顯)
                "yAxes": [{
                    "ticks": {
                        "beginAtZero": False
                    }
                }],
                "xAxes": [{
                    "ticks": {
                        "autoSkip": True,
                        "maxTicksLimit": 10
                    }
                }]
            },
            "elements": {
                "line": {
                    "tension": 0
                }
            },
            "layout": {
                "padding": {
                    "left": 10,
                    "right": 10,
                    "top": 10,
                    "bottom": 10
                }
            }
        }
    }
    
    # 改用 Short URL API (POST) 以避免 URL 過長 (超過 2000 字元)
    try:
        url = "https://quickchart.io/chart/create"
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 600,
            "backgroundColor": "white"
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            return response.json().get('url')
        else:
            print(f"QuickChart Error: {response.text}")
            return None
    except Exception as e:
        print(f"Error generating chart URL: {e}")
        return None

def get_stock_info(symbol):
    """
    取得台股即時資訊 (Yahoo Finance)
    """
    try:
        stock = yf.Ticker(f"{symbol}.TW")
        # fast_info 通常比 info 快且欄位較穩定
        info = stock.fast_info
        
        # 取得基本資料
        current_price = info.last_price
        prev_close = info.previous_close
        
        # 計算漲跌
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        # 漲跌停價格 (台股 10%)
        limit_up = prev_close * 1.10
        limit_down = prev_close * 0.90
        
        # 其他資訊
        volume = info.last_volume
        day_high = info.day_high
        day_low = info.day_low
        
        try:
            detailed_info = stock.info
            avg_price = detailed_info.get('fiftyDayAverage', 0)
            name = detailed_info.get('longName', symbol)
        except:
            avg_price = 0
            name = symbol
            
        return {
            "symbol": symbol,
            "name": name,
            "price": current_price,
            "change": change,
            "change_percent": change_percent,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "volume": volume,
            "high": day_high,
            "low": day_low,
            "avg_price": avg_price
        }
    except Exception as e:
        print(f"Error fetching stock info: {e}")
        return None

def generate_stock_flex_message(data):
    """
    產生台股資訊 Flex Message
    """
    symbol = data['symbol']
    name = data['name']
    price = data['price']
    change = data['change']
    percent = data['change_percent']
    
    # 顏色邏輯
    if change > 0:
        color = "#eb4e3d" # Red
        sign = "+"
    elif change < 0:
        color = "#27ba46" # Green
        sign = ""
    else:
        color = "#333333" # Black
        sign = ""
        
    return FlexSendMessage(
        alt_text=f"{name} 股價資訊",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{name} ({symbol})", weight='bold', size='xl'),
                    BoxComponent(
                        layout='baseline',
                        margin='md',
                        contents=[
                            TextComponent(text=f"{price:.2f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{change:.2f} ({sign}{percent:.2f}%)", size='sm', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=[
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="漲停", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['limit_up']:.2f}", align='end', color='#eb4e3d', size='sm', flex=2),
                                    TextComponent(text="跌停", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['limit_down']:.2f}", align='end', color='#27ba46', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="最高", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['high']:.2f}", align='end', size='sm', flex=2),
                                    TextComponent(text="最低", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['low']:.2f}", align='end', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="總量", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['volume']:,.0f}", align='end', size='sm', flex=2),
                                    TextComponent(text="50日均", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{(data.get('avg_price') or 0):.2f}", align='end', size='sm', flex=2)
                                ]
                            )
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical',
                        margin='md',
                        spacing='sm',
                        contents=[
                            ButtonComponent(
                                style='primary',
                                height='sm',
                                action=MessageAction(label='即時走勢圖', text=f'{symbol} 即時')
                            ),
                            BoxComponent(
                                layout='horizontal',
                                spacing='sm',
                                contents=[
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='日 K', text=f'{symbol} 日K')),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='週 K', text=f'{symbol} 週K')),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='月 K', text=f'{symbol} 月K'))
                                ]
                            ),
                            ButtonComponent(
                                style='link',
                                height='sm',
                                action=MessageAction(label='近3日交易量', text=f'{symbol} 交易量')
                            )
                        ]
                    )
                ]
            )
        )
    )

def generate_kline_chart_url(symbol, period="1mo", interval="1d", title_suffix="日K"):
    """
    產生 K 線圖、即時走勢圖或成交量圖 URL (QuickChart)
    """
    try:
        stock = yf.Ticker(f"{symbol}.TW")
        hist = stock.history(period=period, interval=interval)
        
        if hist.empty:
            return None

        # -----------------------------------------------
        # Case A: 即時走勢 (Intraday) -> Line Chart
        # -----------------------------------------------
        if "即時" in title_suffix or interval in ['1m', '2m', '5m', '15m']:
            # ... (Previous Line Chart Logic) ...
            dates = []
            prices = []
            for index, row in hist.iterrows():
                dt_str = index.strftime('%H:%M')
                dates.append(dt_str)
                prices.append(row['Close'])

            chart_config = {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [{
                        "label": f"{symbol} 即時",
                        "data": prices,
                        "borderColor": "#eb4e3d",
                        "fill": False,
                        "pointRadius": 0,
                        "borderWidth": 2,
                        "lineTension": 0.1
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{symbol} 即時走勢 (Close)"},
                    "scales": {
                        "yAxes": [{"ticks": {"beginAtZero": False}}],
                        "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 10}}] 
                    }
                }
            }
            version = '2.9.4' # Line chart works fine on v2

        # -----------------------------------------------
        # Case B: 三日交易量 (Volume) -> Bar Chart
        # -----------------------------------------------
        elif "交易量" in title_suffix:
            # 取最近 3 天
            recent_data = hist.tail(3)
            labels = []
            volumes = []
            colors = []
            
            for index, row in recent_data.iterrows():
                date_str = index.strftime('%m/%d')
                labels.append(date_str)
                vol = row['Volume']
                volumes.append(vol)
                # Color based on price change (approx)
                # Simple logic: positive close-open usually red, else green.
                # Just fix to Gray/Blue for volume to avoid confusion? 
                # Or use Red/Green (Red=Up).
                if row['Close'] >= row['Open']:
                    colors.append('rgba(235, 78, 61, 0.7)') # Red
                else:
                    colors.append('rgba(39, 186, 70, 0.7)') # Green

            chart_config = {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "成交量",
                        "data": volumes,
                        "backgroundColor": colors
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{symbol} 近三日成交量"},
                    "scales": {
                        "yAxes": [{"ticks": {"beginAtZero": True}}]
                    },
                    "legend": {"display": False}
                }
            }
            version = '2.9.4'

        # -----------------------------------------------
        # Case C: 歷史 K 線 (Candlestick) -> Candlestick Chart
        # -----------------------------------------------
        else:
            # ... (Previous Candlestick logic) ...
            ohlc_data = []
            recent_data = hist.tail(60)
            labels = []
            
            for index, row in recent_data.iterrows():
                # 注意: QuickChart v3 plugin 格式可能需要 'x', 'o', 'h', 'l', 'c'
                date_str = index.strftime('%Y-%m-%d')
                labels.append(date_str)
                ohlc_data.append({
                    "x": date_str, 
                    "o": row['Open'],
                    "h": row['High'],
                    "l": row['Low'],
                    "c": row['Close']
                })
            
            chart_config = {
                "type": "candlestick",
                "data": {
                    "labels": labels, 
                    "datasets": [{
                        "label": f"{symbol}", # Suffix removed to save space
                        "data": ohlc_data,
                        # Candlestick colors
                        "color": {
                            "up": "#eb4e3d",
                            "down": "#27ba46",
                            "unchanged": "#999"
                        }
                    }]
                },
                "options": {
                     "plugins": {
                        "title": { # v3 syntax
                            "display": True,
                            "text": f"{symbol} {title_suffix}"
                        },
                        "legend": {"display": False}
                     },
                     "scales": {
                        "y": { # v3 syntax
                            "ticks": {"beginAtZero": False} 
                        }
                    }
                }
            }
            version = '3' # Force v3 for better candlestick support

        # API Call
        url = "https://quickchart.io/chart/create"
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 600,
            "backgroundColor": "white",
            "version": version # Specify version
        }
        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            return response.json().get('url')
        return None
    except Exception as e:
        print(f"Error generating chart: {e}")
        return None

# --- 路由設定 ---
@app.route("/", methods=['GET'])
def home():
    return "Hello! I am alive!", 200
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/push_report", methods=['GET'])
def push_report():
    if not TARGET_ID:
        return "Target ID not set.", 500
    
    # 取得動態問候語
    greeting = get_greeting()
    report = get_taiwan_bank_rates("HKD")
    
    try:
        # 訊息內容：加入動態問候語
        msg_content = f"{greeting}！每日匯率快報 (現鈔賣出)\n\n{report}"
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=msg_content))
        return "Sent!", 200
    except Exception as e:
        return f"Error: {e}", 500

@handler.add(JoinEvent)
def handle_join(event):
    group_id = event.source.group_id
    welcome_msg = f"大家好！本群組 ID:\n{group_id}\n請設定到 Render 環境變數 TARGET_ID。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_msg))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.upper().strip()
    
    # ID 查詢指令
    if msg in ['ID', '我的ID']:
        if event.source.type == 'group':
            target_id = event.source.group_id
        else:
            target_id = event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID: {target_id}"))
        return

    # 處理被標註的情況
    try:
        is_mentioned = False
        
        # 方法 1: 檢查 event 中的 mention 物件 (最準確)
        if hasattr(event.message, 'mention') and event.message.mention:
            # 嘗試取得機器人自身的 User ID (快取)
            global BOT_USER_ID
            if 'BOT_USER_ID' not in globals() or not BOT_USER_ID:
                try:
                    bot_info = line_bot_api.get_bot_info()
                    BOT_USER_ID = bot_info.user_id
                except:
                    BOT_USER_ID = None
            
            # 比對 mention 列表
            if BOT_USER_ID:
                for mentionee in event.message.mention.mentionees:
                    if mentionee.user_id == BOT_USER_ID:
                        is_mentioned = True
                        break
        
        # 方法 2: 如果無法取得 ID 或沒有 mention 物件，退回文字比對 (模糊比對)
        # 用戶可能把機器人改名，所以檢查是否包含 "@" 且長度較短，或特定關鍵字
        if not is_mentioned:
             if '@LINEBOT' in msg or ('@' in msg and '機器人' in msg):
                 is_mentioned = True

        if is_mentioned:
            # 取得發送者 User ID
            user_id = event.source.user_id
            
            try:
                # 判斷來源類型以使用正確的 API
                if event.source.type == 'group':
                    profile = line_bot_api.get_group_member_profile(event.source.group_id, user_id)
                elif event.source.type == 'room':
                    profile = line_bot_api.get_room_member_profile(event.source.room_id, user_id)
                else:
                    profile = line_bot_api.get_profile(user_id)
                
                user_name = profile.display_name
            except:
                # 無法取得個人資料時的預設名稱
                user_name = "朋友"

            # 取得問候語
            greeting = get_greeting()
            
            # 特殊稱號邏輯
            # 針對每個使用者後面都加大帥哥 (Modified request)
            user_name += " 大帥哥"
            
            reply_text = f"{user_name} {greeting}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return
            
    except Exception as e:
        # 發生錯誤時的 fallback
        # 如果確定是被標註(前面邏輯 pass)，但後面出錯，回個簡單的
        pass

    # 匯率查詢
    if msg in VALID_CURRENCIES:
        report = get_taiwan_bank_rates(msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=report))
        return

    # 匯率走勢圖指令
    # 支援: "USD圖", "USD 走勢", "USD CHART", "美金圖" ... etc
    # 簡單起見，檢查是否包含 currency code 且 (長度 > 3)
    # 或者 users natural language: "可以去觀察一段時間的匯率 並畫出折線圖嗎" -> 太複雜，先做 suffix
    
    chart_currency = None
    if '圖' in msg or '走勢' in msg or 'CHART' in msg:
        for cur in VALID_CURRENCIES:
            if cur in msg:
                chart_currency = cur
                break
    
    if chart_currency:
        try:
            dates, cash_rates, spot_rates = get_historical_data(chart_currency)
            if dates and (any(cash_rates) or any(spot_rates)):
                chart_url = generate_chart_url(dates, cash_rates, spot_rates, chart_currency)
                if chart_url:
                    line_bot_api.reply_message(event.reply_token, ImageSendMessage(
                        original_content_url=chart_url,
                        preview_image_url=chart_url
                    ))
                else:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="產生圖表失敗 (URL Error)"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"無法取得 {chart_currency} 歷史數據 (無資料)"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"處理圖表時發生錯誤: {str(e)}"))
        return

    # --- 台股指令處理 ---
    # 1. 股票代號查詢: 即時報價 Flex Message
    # 放寬檢查: 只要是英數字且長度在 4~6 之間 (台股代號通常 4-6 碼)
    if msg.isalnum() and 4 <= len(msg) <= 6:
        # 排除誤判: 如果全是英文可能是貨幣或其他指令，簡單過濾
        # e.g. "TEST" -> pass, "2330" -> ok, "00981A" -> ok
        # 策略: 如果不是純數字，必須包含數字 (e.g. 00981A)
        # 或者乾脆都試試看 get_stock_info，失敗就算了
        
        stock_data = get_stock_info(msg)
        if stock_data:
            flex_msg = generate_stock_flex_message(stock_data)
            line_bot_api.reply_message(event.reply_token, flex_msg)
            return
        # 如果找不到資料，就讓它 pass，避免誤觸其他邏輯
        
    # 2. 股票詳細指令 (e.g., 2330 即時, 2330 日K, 00981A 日K)
    # 檢查是否為 "{代號} {指令}" 格式
    parts = msg.split()
    if len(parts) >= 2:
        symbol = parts[0]
        # 檢查 symbol 是否為合法代號 (英數字)
        if symbol.isalnum() and 4 <= len(symbol) <= 6:
            cmd = parts[1]
            
            url = None
            # 即時走勢 (當日)
            if '即時' in cmd:
                # 取得當日走勢 (1d, 5m)
                url = generate_kline_chart_url(symbol, period="1d", interval="5m", title_suffix="即時走勢")
            
            # 交易量
            elif '交易量' in cmd:
                url = generate_kline_chart_url(symbol, period="5d", interval="1d", title_suffix="交易量")
            
            # K線圖
            elif 'K' in cmd:
                period = "1mo"
                interval = "1d"
                suffix = "日K"
                
                if '日' in cmd:
                    suffix = "日K"
                    period = "3mo" # default 3 months for daily
                elif '週' in cmd:
                    suffix = "週K"
                    period = "1y"  # 1 year for weekly
                    interval = "1wk"
                elif '月' in cmd:
                    suffix = "月K"
                    period = "5y"  # 5 years for monthly
                    interval = "1mo"
                    
                url = generate_kline_chart_url(symbol, period, interval, suffix)
                
            if url:
                line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
            else:
                # 失敗時回報，方便除錯
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"無法產生 {symbol} 圖表 (無資料或 API 錯誤)"))
            return

    # 其他情況保持安靜
    else:
        pass

if __name__ == "__main__":
    app.run()