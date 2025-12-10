from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import os

app = Flask(__name__)

# --- 設定區 (請換成您自己的 Token 和 Secret) ---
# 建議之後改用環境變數 os.environ.get('LINE_CHANNEL_ACCESS_TOKEN') 以保安全
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 監聽所有來自 /callback 的 Post Request ---
@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 表頭
    signature = request.headers['X-Line-Signature']
    # 取得 request body
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 處理訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.upper().strip()  # 轉大寫並去空白
    
    # 簡單的匯率查詢邏輯
    # 使用免費 API: ExchangeRate-API (這裡示範查詢該幣別對 TWD 的匯率)
    try:
        # 呼叫 API
        api_url = f"https://api.exchangerate-api.com/v4/latest/{user_msg}"
        response = requests.get(api_url)
        
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get('TWD') # 預設查詢換成台幣
            
            if rate:
                reply_text = f"目前的 {user_msg} 對台幣 (TWD) 匯率為：{rate}"
            else:
                reply_text = f"找不到 {user_msg} 對台幣的匯率資料。"
        else:
            reply_text = "找不到該幣別，請輸入標準代碼 (例如: USD, JPY, EUR)"
            
    except Exception as e:
        # 如果使用者輸入的不是幣別代碼，或是 API 錯誤
        reply_text = "請輸入正確的貨幣代碼，例如：USD、JPY"

    # 回傳訊息給使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
