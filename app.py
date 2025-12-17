import os
import requests
import pandas as pd
from datetime import datetime
import pytz  # 用來處理時區
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
            # 取得使用者個人資料
            profile = line_bot_api.get_profile(user_id)
            user_name = profile.display_name
            
            # 取得問候語
            greeting = get_greeting()
            
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
    
    # 其他情況保持安靜
    else:
        pass

if __name__ == "__main__":
    app.run()