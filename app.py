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

def get_taiwan_bank_rates(currency_code="HKD"):
    try:
        url = f"https://www.findrate.tw/{currency_code}/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 抓取網頁
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' 
        
        # 解析所有表格
        dfs = pd.read_html(response.text)
        
        # 【關鍵修正】根據您的檔案結構，目標是第二張表格 (索引 1)
        # 加入防呆：如果抓不到第二張，就試著找欄位數對的那張
        target_df = None
        
        if len(dfs) >= 2:
            target_df = dfs[1]
        else:
            # 備用方案：搜尋欄位數大於 5 的表格
            for df in dfs:
                if len(df.columns) > 5:
                    target_df = df
                    break
        
        if target_df is None:
            return "抓取失敗：找不到匯率表格。"

        # 準備輸出文字
        result_text = f"🏆 {currency_code} 現鈔賣出匯率前 5 名:\n"
        result_text += "(⬇️ 數字越低越好 | 更新時間)\n"
        result_text += "----------------\n"
        
        bank_rates = []
        
        # 遍歷每一列資料
        # 使用 iloc 確保我們是用「位置」來抓資料，不受標題名稱影響
        # 跳過第一列 (通常是標題)
        for i in range(len(target_df)):
            try:
                row = target_df.iloc[i]
                
                # 轉成字串並去除空白
                # Index 0: 銀行名稱
                # Index 2: 現鈔賣出 (我們需要的)
                # Index 5: 更新時間 (我們需要的)
                
                bank_name = str(row[0]).strip()
                cash_selling = str(row[2]).strip()
                update_time = str(row[5]).strip()
                
                # 排除標題列 (有些標題列第一欄就是 '銀行名稱')
                if "銀行" in bank_name: continue
                
                # 排除沒有現鈔業務的銀行 (顯示 --)
                if cash_selling == '--': continue

                # 轉換匯率為數字
                rate = float(cash_selling)
                
                bank_rates.append({
                    "bank": bank_name,
                    "rate": rate,
                    "time": update_time
                })
                
            except Exception:
                # 這一行資料有問題就跳過
                continue

        # 1. 排序：由低到高 (最划算在前)
        bank_rates.sort(key=lambda x: x['rate'])

        # 2. 取前 5 名
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            return "查無資料：可能今日所有銀行皆無現鈔報價。"

        # 3. 輸出結果 (格式化小數點後三位)
        for i, item in enumerate(top_5_banks, 1):
            if i == 1: icon = "🥇"
            elif i == 2: icon = "🥈"
            elif i == 3: icon = "🥉"
            else: icon = f" {i}."

            # 格式範例：🥇 上海商銀 (10:30): 4.060
            result_text += f"{icon} {item['bank']} ({item['time']}): {item['rate']:.3f}\n"
            
        return result_text
        
    except Exception as e:
        return f"系統錯誤: {str(e)}"

# --- Webhook 與 路由設定 ---
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
    
    if msg in ['ID', '我的ID']:
        if event.source.type == 'group':
            target_id = event.source.group_id
        else:
            target_id = event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID: {target_id}"))
        return

    # 輸入 3 個字代碼 (如 HKD) 查詢
    if len(msg) == 3:
        report = get_taiwan_bank_rates(msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=report))

if __name__ == "__main__":
    app.run()