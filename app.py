import os
import requests
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)
# --- 新增這個首頁路徑，用來讓外部服務 Ping ---
@app.route("/", methods=['GET'])
def home():
    return "Hello! I am alive!", 200
    
# --- 設定區 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
# 這裡的變數名稱我們沿用 MY_USER_ID，但實際上填入 Group ID 也是可以通的
TARGET_ID = os.environ.get('MY_USER_ID', '') 

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_taiwan_bank_rates(currency_code="HKD"):
    try:
        url = f"https://www.findrate.tw/{currency_code}/" 
        dfs = pd.read_html(url, encoding='utf-8')
        df = dfs[0]
        
        # 標題優化：標註是賣出價前五名
        result_text = f"🏆 {currency_code} 匯率最優前 5 名 (銀行賣出價):\n"
        result_text += "(⬇️ 數字越低越划算)\n"
        result_text += "----------------\n"
        
        bank_rates = []
        
        for index, row in df.iterrows():
            try:
                bank_name = str(row[0])
                if "銀行" in bank_name: continue

                # 優先抓取「即期賣出」(網銀優惠)，若沒有則抓「現金賣出」
                spot_selling = row[4] # 即期
                cash_selling = row[2] # 現金
                
                rate_str = str(spot_selling).strip()
                if rate_str == '--':
                    rate_str = str(cash_selling).strip()

                if rate_str == '--': continue

                rate = float(rate_str)
                bank_rates.append((bank_name, rate))
            except:
                continue

        # 1. 排序：由小到大 (因為賣出價越低越好)
        bank_rates.sort(key=lambda x: x[1])

        # 2. 【關鍵修改】只取前 5 名 (Slice)
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            return "抓取失敗：找不到有效匯率資料。"

        # 3. 漂亮排版：加上獎牌
        for i, (bank, rate) in enumerate(top_5_banks, 1):
            # 只有前三名給獎牌
            if i == 1:
                rank_icon = "🥇"
            elif i == 2:
                rank_icon = "🥈"
            elif i == 3:
                rank_icon = "🥉"
            else:
                rank_icon = f" {i}."

            formatted_rate = f"{rate:.3f}"
            result_text += f"{rank_icon} {bank}: {formatted_rate}\n"
            
        return result_text
        
    except Exception as e:
        return f"讀取匯率失敗。\n錯誤訊息: {str(e)}"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- Cron Job 定時推播入口 ---
@app.route("/push_report", methods=['GET'])
def push_report():
    if not TARGET_ID:
        return "尚未設定 MY_USER_ID (TARGET_ID)，無法推播。", 500
    
    report = get_taiwan_bank_rates("HKD")
    
    try:
        # 這裡的 TARGET_ID 如果是 C 開頭的群組 ID，LINE 也會正確推送到群組
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=f"🌞 早安！每日匯率快報 (8:00)\n\n{report}"))
        return "Message sent!", 200
    except Exception as e:
        return f"Error: {e}", 500

# --- 處理訊息 (修改過) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.upper().strip()
    
    # 修改：分辨是個人還是群組，並回傳正確的 ID
    if msg in ['ID', '我的ID']:
        if event.source.type == 'group':
            target_id = event.source.group_id
            type_text = "本群組的 Group ID"
        elif event.source.type == 'room':
            target_id = event.source.room_id
            type_text = "聊天室 Room ID"
        else:
            target_id = event.source.user_id
            type_text = "您的個人 User ID"
            
        reply = f"📍 {type_text} 是：\n{target_id}\n\n請複製這串 ID (C開頭代表群組)，去 Render 更新 'MY_USER_ID' 變數。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 一般查詢匯率功能
    if len(msg) == 3:
        report = get_taiwan_bank_rates(msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=report))
    else:
        # 在群組裡，如果隨便講話機器人都回，會很吵。
        # 這裡建議：除非輸入 ID 或 3個字的幣別，否則機器人保持安靜。
        pass 

if __name__ == "__main__":
    app.run()