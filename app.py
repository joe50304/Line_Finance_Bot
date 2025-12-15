import os
import requests
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent

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

def get_taiwan_bank_rates(currency_code="HKD"):
    try:
        url = f"https://www.findrate.tw/{currency_code}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' 
        
        dfs = pd.read_html(response.text)
        
        # 抓取表格 (嘗試抓取第 2 張)
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
                cash_selling = str(row[2]).strip() # 現鈔賣出
                update_time = str(row[5]).strip()
                
                if "銀行" in bank_name or cash_selling == '--': continue

                rate = float(cash_selling)
                bank_rates.append({
                    "bank": bank_name,
                    "rate": rate,
                    "time": update_time
                })
            except:
                continue

        bank_rates.sort(key=lambda x: x['rate'])
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            return f"雖然有 {currency_code} 的頁面，但今日無銀行提供「現鈔」賣出報價。"

        for i, item in enumerate(top_5_banks, 1):
            if i == 1: icon = "🥇"
            elif i == 2: icon = "🥈"
            elif i == 3: icon = "🥉"
            else: icon = f" {i}."
            result_text += f"{icon} {item['bank']} ({item['time']}): {item['rate']}\n" # 這裡不強制 .3f，依網站顯示為主，以免位數不同
            
        return result_text
        
    except Exception as e:
        return f"查詢失敗: {str(e)}"

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
    report = get_taiwan_bank_rates("HKD")
    try:
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=f"🌞 早安！每日匯率 (現鈔賣出)\n\n{report}"))
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

    # 匯率查詢 (白名單過濾)
    if msg in VALID_CURRENCIES:
        report = get_taiwan_bank_rates(msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=report))
    
    # 3. 其他情況保持安靜 (pass)
    else:
        pass

if __name__ == "__main__":
    app.run()