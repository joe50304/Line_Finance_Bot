import os
import requests
import pandas as pd
import io  # <--- 新增這個套件，用來解決爬蟲報錯問題
from datetime import datetime
import pytz
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

# --- 1. 問候語 ---
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
        
        # 【關鍵修正】使用 io.StringIO 包裝，避免 pandas 把 HTML 當成檔名
        html_buffer = io.StringIO(response.text)
        dfs = pd.read_html(html_buffer)
        
        target_df = None
        for df in dfs:
            # 必須包含 "現鈔賣出" 才是我們要的表格
            # 轉為 string 來搜尋關鍵字
            cols_str = str(df.columns)
            if "現鈔賣出" in cols_str: 
                 target_df = df
                 break
        
        # Fallback: if not found, check if any table has enough columns and looks like it
        if target_df is None:
            for df in dfs:
                if len(df.columns) >= 5 and "銀行" in str(df.columns):
                    target_df = df
                    break
        
        if target_df is None:
            return f"找不到 {currency_code} 的匯率表格，可能該網站未提供。"

        # 0=銀行, 1=現鈔買入, 2=現鈔賣出, 3=即期買入, 4=即期賣出, 5=更新時間
        # 準備輸出文字報告 (已廢棄 purely text return，改回傳 list 給 Flex Message 用)
        # 為了相容舊邏輯，我們這裡回傳 dict 列表，如果 caller 是舊的再轉字串 (但我們會更新 caller)
        
        bank_rates = []
        
        for i in range(len(target_df)):
            try:
                row = target_df.iloc[i]
                bank_name = str(row.iloc[0]).strip()
                cash_selling = str(row.iloc[2]).strip() # 現鈔賣出
                spot_selling = str(row.iloc[4]).strip() # 即期賣出
                # Col 5 is usually time
                update_time = str(row.iloc[5]).strip()

                if bank_name in ["銀行名稱", "銀行", "幣別"]: continue
                if cash_selling == '--' and spot_selling == '--': continue
                if len(bank_name) > 20: continue

                # 處理數值 (優先排現鈔，若無現鈔排即期)
                rate_val = 9999.0
                try: rate_val = float(cash_selling)
                except: 
                    try: rate_val = float(spot_selling)
                    except: pass
                
                bank_rates.append({
                    "bank": bank_name,
                    "cash_selling": cash_selling,
                    "spot_selling": spot_selling,
                    "rate_sort": rate_val,
                    "time": update_time
                })
            except: continue

        bank_rates.sort(key=lambda x: x['rate_sort'])
        return bank_rates[:10] # 回傳前 10 名 list
        
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []
        
    except Exception as e:
        # 只回傳簡短錯誤，避免塞爆 LINE
        return f"查詢失敗: {str(e)[:100]}..."

# --- 3. API：Yahoo Finance (國際匯率) ---
def get_forex_info(currency_code):
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
    產生匯率走勢圖
    """
    try:
        symbol = f"{currency_code}TWD=X"
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        # Fallback 1: 1d 沒資料 -> 抓 5d
        if data.empty and period == '1d':
            period = '5d'
            interval = '60m'
            data = ticker.history(period=period, interval=interval)

        # Fallback 2: 1y 沒資料 (偶爾發生) -> 嘗試抓 6mo
        if data.empty and period == '1y':
            period = '6mo'
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

        # 【關鍵修正】縮減資料點 (QuickChart URL 長度限制)
        # 如果資料點超過 60 個，就進行抽樣，確保 1Y 圖表能顯示
        if len(dates) > 60:
            step = len(dates) // 60 + 1
            dates = dates[::step]
            prices = prices[::step]

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

# --- 5. Flex Message ---
def generate_currency_flex_message(forex_data, bank_report_text):
    c_code = forex_data['currency']
    price = forex_data['price']
    change = forex_data['change']
    percent = forex_data['change_percent']
    
    if change > 0: color = "#eb4e3d"; sign = "+"
    elif change < 0: color = "#27ba46"; sign = ""
    else: color = "#333333"; sign = ""

    # Build Top 5 Banks Rows
    bank_rows = []
    # Header
    bank_rows.append(
        BoxComponent(
            layout='horizontal',
            contents=[
                TextComponent(text="銀行", size='xxs', color='#aaaaaa', flex=3),
                TextComponent(text="現鈔賣出", size='xxs', color='#aaaaaa', align='end', flex=2),
                TextComponent(text="即期賣出", size='xxs', color='#aaaaaa', align='end', flex=2)
            ]
        )
    )
    
    # Data Rows
    # bank_report_text is now a LIST of dicts based on our change to get_taiwan_bank_rates
    # But wait, we need to handle if it's still a string (error message) or list
    if isinstance(bank_report_text, list):
        for i, b in enumerate(bank_report_text[:5]): # Top 5
            row_color = "#333333"
            if i == 0: row_color = "#eb4e3d" # Top 1 highlight
            
            bank_rows.append(
                BoxComponent(
                    layout='horizontal', margin='xs',
                    contents=[
                        TextComponent(text=b['bank'], size='xs', color=row_color, flex=3, weight='bold' if i==0 else 'regular'),
                        TextComponent(text=b['cash_selling'], size='xs', color=row_color, align='end', flex=2),
                        TextComponent(text=b['spot_selling'], size='xs', color='#555555', align='end', flex=2)
                    ]
                )
            )
    else:
        # Fallback if error string
        bank_rows.append(TextComponent(text=str(bank_report_text), size='xs', color='#ff0000'))


    return FlexSendMessage(
        alt_text=f"{c_code} 匯率快報",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{c_code}/TWD 匯率", weight='bold', size='xl', color='#555555'),
                    TextComponent(text="台灣時間即時行情 (Yahoo)", size='xxs', color='#aaaaaa'),
                    BoxComponent(
                        layout='baseline', margin='md',
                        contents=[
                            TextComponent(text=f"{price:.4f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{change:.4f} ({sign}{percent:.2f}%)", size='xs', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    TextComponent(text="🇹🇼 台灣銀行最佳匯率 (Top 5)", size='sm', weight='bold', color='#555555', margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='md', spacing='xs',
                        contents=bank_rows
                    ),
                    SeparatorComponent(margin='lg'),
                    TextComponent(text="歷史走勢圖:", size='xs', color='#aaaaaa', margin='md'),
                    BoxComponent(
                        layout='horizontal', margin='sm', spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1日走勢', text=f'{c_code} 1D')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='5日走勢', text=f'{c_code} 5D'))
                        ]
                    ),
                    BoxComponent(
                        layout='horizontal', margin='sm', spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1月走勢', text=f'{c_code} 1M')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1年走勢', text=f'{c_code} 1Y'))
                        ]
                    ),
                    ButtonComponent(style='link', height='sm', action=MessageAction(label='查看完整銀行比價', text=f'{c_code} 列表'))
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

# --- 台股功能 (保留) ---
def get_valid_stock_obj(symbol):
    def fetch(t):
        try: s = yf.Ticker(t); return s, s.fast_info
        except: return None, None
    for suffix in [".TW", ".TWO"]:
        s, i = fetch(symbol + suffix)
        if i and hasattr(i, 'last_price') and i.last_price: return s, i, suffix
    return None, None, None


# 補充: 取得 TWSE 額外資訊 (PE/PB/Yield)
@cached(TTLCache(maxsize=1, ttl=300))
def get_twse_stats():
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            stats = {}
            for item in data:
                code = item.get('Code')
                stats[code] = {
                    "PE": item.get('PEratio', '-'), 
                    "Yield": item.get('DividendYield', '-'),
                    "PB": item.get('PBratio', '-')
                }
            return stats
    except: pass
    return {}

def get_stock_info(symbol):
    try:
        stock, info, suffix = get_valid_stock_obj(symbol)
        if not stock: return None
        
        # 嘗試取得額外資訊
        avg_price = 0
        try:
            # Note: detailed info might be slow
            # avg_price = stock.info.get('fiftyDayAverage', 0)
            pass 
        except: pass

        extra_stats = {}
        if suffix == ".TW":
             all_stats = get_twse_stats()
             if symbol in all_stats: extra_stats = all_stats[symbol]

        return {
            "symbol": symbol, "name": symbol,
            "price": info.last_price, "change": info.last_price - info.previous_close,
            "change_percent": (info.last_price - info.previous_close)/info.previous_close*100,
            "limit_up": info.previous_close*1.1, "limit_down": info.previous_close*0.9,
            "volume": info.last_volume, "high": info.day_high, "low": info.day_low,
            "avg_price": avg_price,
            "type": "上櫃" if suffix == ".TWO" else "上市",
            "twse_stats": extra_stats
        }
    except: return None

def generate_stock_flex_message(data):
    color = "#eb4e3d" if data['change'] > 0 else "#27ba46" if data['change'] < 0 else "#333333"
    sign = "+" if data['change'] > 0 else ""
    
    return FlexSendMessage(
        alt_text=f"{data['symbol']} 股價",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{data['name']} ({data['symbol']})", weight='bold', size='xl'),
                    BoxComponent(
                        layout='baseline', margin='md',
                        contents=[
                            TextComponent(text=f"{data['price']:.2f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{data['change']:.2f} ({sign}{data['change_percent']:.2f}%)", size='sm', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='lg', spacing='sm',
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
                                    TextComponent(text="類型", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['type']}", align='end', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="本益比", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data.get('twse_stats', {}).get('PE', '-')}", align='end', size='sm', flex=2),
                                    TextComponent(text="殖利率", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data.get('twse_stats', {}).get('Yield', '-')}%" if data.get('twse_stats', {}).get('Yield', '-') != '-' else '-', align='end', size='sm', flex=2)
                                ]
                            )
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='md', spacing='sm',
                        contents=[
                            ButtonComponent(
                                style='primary', height='sm',
                                action=MessageAction(label='即時走勢圖', text=f"{data['symbol']} 即時")
                            ),
                            BoxComponent(
                                layout='horizontal', spacing='sm',
                                contents=[
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='日 K', text=f"{data['symbol']} 日K")),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='週 K', text=f"{data['symbol']} 週K")),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='月 K', text=f"{data['symbol']} 月K"))
                                ]
                            ),
                            ButtonComponent(style='link', height='sm', action=MessageAction(label='近3日交易量', text=f"{data['symbol']} 交易量"))
                        ]
                    )
                ]
            )
        )
    )

def generate_stock_chart_url_yf(symbol, period="1d", interval="15m", chart_type="line"):
    """
    產生台股走勢圖 (自動判斷上市/上櫃)
    chart_type: 'line', 'candlestick', 'bar' (for volume)
    """
    try:
        # 判斷是上市還是上櫃
        stock, info, suffix = get_valid_stock_obj(symbol)
        if not stock: return None
        
        full_symbol = symbol + suffix
        ticker = yf.Ticker(full_symbol)
        
        # Volume 需要 'Volume' column, K-line calls API properly
        data = ticker.history(period=period, interval=interval)
        
        if data.empty: return None

        # ----------------------------
        # 1. 折線圖 (Line Chart) Logic
        # ----------------------------
        if chart_type == 'line':
            dates = []
            prices = []
            
            for index, row in data.iterrows():
                if period == '1d':
                    dt_str = index.strftime('%H:%M')
                elif period in ['5d', '1mo']:
                    dt_str = index.strftime('%m/%d')
                else:
                    dt_str = index.strftime('%Y-%m')
                    
                dates.append(dt_str)
                prices.append(row['Close'])

            # 抽樣：避免 URL 過長
            if len(dates) > 60:
                step = len(dates) // 60 + 1
                dates = dates[::step]
                prices = prices[::step]

            color = "#eb4e3d" if prices[-1] >= prices[0] else "#27ba46"
            
            chart_config = {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [{
                        "label": f"{symbol} ({period})",
                        "data": prices,
                        "borderColor": color,
                        "backgroundColor": f"{color}1A",
                        "fill": True,
                        "pointRadius": 0,
                        "borderWidth": 2,
                        "lineTension": 0.1
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{symbol} 股價走勢" if period == '1d' else f"{symbol} 股價走勢 ({period})"},
                    "legend": {"display": False},
                    "scales": {
                        "yAxes": [{"ticks": {"beginAtZero": False}}],
                        "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 6}}] 
                    }
                }
            }

        # ----------------------------
        # 2. K線圖 (Candlestick) Logic
        # ----------------------------
        elif chart_type == 'candlestick':
            # 抽樣：QuickChart 對 K 線圖的 Payload 限制較嚴格
            if len(data) > 60:
                 step = len(data) // 60 + 1
                 data = data.iloc[::step]

            ohlc_data = []
            for index, row in data.iterrows():
                # Note: timestamps handling for QuickChart candlestick
                # x value can be milliseconds or string date. String date is safer for display.
                # However, for Candlestick, usually 't' (timestamp ms) is reliable.
                ts = int(index.timestamp() * 1000)
                ohlc_data.append({
                    "t": ts,
                    "o": float(row['Open']),
                    "h": float(row['High']),
                    "l": float(row['Low']),
                    "c": float(row['Close'])
                })
                
            chart_config = {
                "type": "candlestick",
                "data": {
                    "datasets": [{
                        "label": f"{symbol} ({period})",
                        "data": ohlc_data
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{symbol} K線圖 ({period})"},
                    "legend": {"display": False},
                    "scales": {
                        "xAxes": [{
                            "type": "time",
                            "time": {
                                "unit": "day" if period != '1d' else 'hour'
                            },
                             "ticks": {"source": "auto"},
                             "gridLines": {"display": False}
                        }],
                         "yAxes": [{
                            "gridLines": {"display": True, "color": "#eeeeee"}
                         }]
                    }
                }
            }

        # ----------------------------
        # 3. 交易量圖 (Volume Bar Chart) Logic
        # ----------------------------
        elif chart_type == 'bar': # 用 bar chart 來畫交易量
             # 抽樣
            if len(data) > 60:
                 step = len(data) // 60 + 1
                 data = data.iloc[::step]
            
            dates = []
            volumes = []
            for index, row in data.iterrows():
                dt_str = index.strftime('%m/%d')
                dates.append(dt_str)
                volumes.append(int(row['Volume']))

            chart_config = {
                "type": "bar",
                "data": {
                    "labels": dates,
                    "datasets": [{
                        "label": "Volume",
                        "data": volumes,
                        "backgroundColor": "#36a2eb"
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{symbol} 交易量 ({period})"},
                    "legend": {"display": False},
                    "scales": {
                        "yAxes": [{"ticks": {"beginAtZero": True}}]
                    }
                }
            }

        # 發送 Request
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
            print(f"QuickChart Error: {response.text}")
            return None

            
    except Exception as e:
        print(f"Stock Chart Error: {e}")
        return None

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
    
    # 0. 處理 Mentions (被標記) & 關鍵字問候
    # 把它移到最前面，並且放寬判斷標準
    is_greeting = False
    greetings = ["HI", "HELLO", "你好", "您好", "早安", "午安", "晚安", "嗨", "TEST", "測試"]
    msg_upper = msg.upper()
    
    # 只要訊息中有問候語，且 (長度很短 OR 有被 Tag) 就回覆
    # 注意: Line 文字中 Tag 會變成 "@Name " (有空格)
    if any(g in msg_upper for g in greetings):
         # 簡單判定：如果句子很短 (< 10 words) 或是包含 "BOT" / "@"
         if len(msg) < 10 or "BOT" in msg_upper or "@" in msg:
             is_greeting = True
    
    # 避免自己回自己: 檢查是否包含 "🤖" (我們自己的 emoji) -> 但 user 說沒回，也許不是這個問題
    # 我們改為不檢查 emoji，畢竟 user 也可以打 emoji
    
    if is_greeting:
        reply_text = f"{get_greeting()}！我是您的金融小幫手 🤖\n輸入 'USD' 查詢匯率\n輸入 '2330' 查詢股價"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    if msg in ['ID', '我的ID']:
        tid = event.source.group_id if event.source.type == 'group' else event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID: {tid}"))
        return

    if msg in ['HELP', 'MENU', '選單']:
        line_bot_api.reply_message(event.reply_token, generate_help_message())
        return

    # 1. 匯率查詢 (儀表板)
    if msg in VALID_CURRENCIES:
        forex_data = get_forex_info(msg)
        bank_report = get_taiwan_bank_rates(msg)
        
        if forex_data:
            flex_msg = generate_currency_flex_message(forex_data, bank_report)
            line_bot_api.reply_message(event.reply_token, flex_msg)
        else:
             # 如果沒有 forex data，但有 bank report (list or str)
             if isinstance(bank_report, list):
                  text_report = f"🏆 {msg} 匯率 (無即時盤)\n----------------\n"
                  for item in bank_report[:10]:
                      text_report += f"{item['bank']}: {item['cash_selling']}\n"
                  line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text_report))
             else:
                  line_bot_api.reply_message(event.reply_token, TextSendMessage(text=str(bank_report)))
        return

    # 2. 匯率完整列表
    parts = msg.split()
    if len(parts) == 2 and parts[1] == '列表' and parts[0] in VALID_CURRENCIES:
        report = get_taiwan_bank_rates(parts[0])
        if len(report) > 0 and isinstance(report, list):
             # 將 list 轉為純文字報告
             text_report = f"🏆 {parts[0]} 匯率總覽\n(銀行 | 現鈔賣出 | 即期賣出)\n----------------\n"
             for item in report:
                 text_report += f"{item['bank']}: {item['cash_selling']} | {item['spot_selling']}\n"
             line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text_report))
        else:
             line_bot_api.reply_message(event.reply_token, TextSendMessage(text=str(report) if report else "查無資料"))
        return

    # 3. 匯率走勢圖
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
            if cmd in ['1D', '5D', '1M', '1Y']:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 暫無該時段走勢數據 (可能為週末或資料源問題)"))
        return


    # 4. 台股複雜指令 (走勢圖/交易量)
    # 指令格式: "{股票代號} {指令}"
    if len(parts) == 2 and parts[0].isdigit():
        symbol = parts[0]
        cmd = parts[1]
        
        chart_url = None
        # 對應 Flex Message 按鈕的文案

        if cmd in ['即時', '即時走勢', '即時走勢圖']:
            chart_url = generate_stock_chart_url_yf(symbol, '1d', '5m', chart_type='line')
        elif cmd in ['日K', '日線']:
            chart_url = generate_stock_chart_url_yf(symbol, '1y', '1d', chart_type='candlestick')
        elif cmd in ['週K', '週線']:
            chart_url = generate_stock_chart_url_yf(symbol, '2y', '1wk', chart_type='candlestick')
        elif cmd in ['月K', '月線']:
            chart_url = generate_stock_chart_url_yf(symbol, '5y', '1mo', chart_type='candlestick')
        elif cmd in ['交易量', '近3日交易量']:
             # 交易量: 使用 Bar Chart, 週期1個月 (看近期量能變化)
             chart_url = generate_stock_chart_url_yf(symbol, '1mo', '1d', chart_type='bar')

        if chart_url:
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=chart_url, preview_image_url=chart_url))
        else:
            # error handling
            if cmd in ['即時', '日K', '週K', '月K', '交易量']:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 產生圖表失敗 ({cmd})"))
        return
    if msg.isascii() and msg.isalnum() and 4 <= len(msg) <= 6:
        stock = get_stock_info(msg)
        if stock:
            line_bot_api.reply_message(event.reply_token, generate_stock_flex_message(stock))
        return

if __name__ == "__main__":
    app.run()