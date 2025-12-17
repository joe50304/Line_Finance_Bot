import os
import requests
import pandas as pd
from datetime import datetime
import pytz  # 用來處理時區
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent, ImageSendMessage

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
            # 判斷邏輯: 檢查欄位是否包含匯率相關字眼，或者欄位數量正確
            # 用戶回饋日期欄位可能空白，且有現鈔/即期
            # 通常表格結構: [日期, 即期買入, 即期賣出, 現鈔買入, 現鈔賣出]
            if len(df.columns) >= 5:
                # 簡單檢查一下內容是否像日期
                try:
                    first_val = str(df.iloc[0, 0])
                    if '20' in first_val and '-' in first_val: # 2024-xx-xx
                        target_df = df
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
            }
        }
    }
    
    # 轉換成 URL 編碼的 JSON 字串
    import json
    import urllib.parse
    
    json_str = json.dumps(chart_config)
    encoded_config = urllib.parse.quote(json_str)
    
    # 建構最終 URL
    return f"https://quickchart.io/chart?c={encoded_config}"

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
        dates, cash_rates, spot_rates = get_historical_data(chart_currency)
        if dates and (any(cash_rates) or any(spot_rates)):
            chart_url = generate_chart_url(dates, cash_rates, spot_rates, chart_currency)
            if chart_url:
                line_bot_api.reply_message(event.reply_token, ImageSendMessage(
                    original_content_url=chart_url,
                    preview_image_url=chart_url
                ))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="產生圖表失敗"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="無法取得歷史數據 (可能無該幣別資料)"))
        return

    # 其他情況保持安靜
    else:
        pass

if __name__ == "__main__":
    app.run()