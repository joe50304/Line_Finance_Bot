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
        
        # 1. 【關鍵修正】偽裝成瀏覽器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 先用 requests 抓取網頁原始碼
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' # 強制設定編碼，避免亂碼
        
        # 2. 解析 HTML
        dfs = pd.read_html(response.text)
        print(dfs)
        if not dfs:
            return "錯誤：找不到任何表格，可能是網站結構改變。"

        # 3. 【關鍵修正】自動尋找正確的表格
        # 我們不假設是 dfs[0]，而是檢查哪一張表格有 "即期賣出" 這些關鍵字
        target_df = None
        for df in dfs:
            # 檢查欄位名稱或內容是否包含關鍵字
            # 將整個 DataFrame 轉成字串來搜尋最快
            if "銀行" in str(df.columns) or "銀行" in df.to_string():
                target_df = df
                print(target_df)
                break
        
        if target_df is None:
            return "錯誤：抓到了表格，但找不到包含匯率資訊的目標表格。"

        # 開始處理資料
        result_text = f"🏆 {currency_code} 匯率最優前 5 名 (銀行賣出價):\n"
        result_text += "(⬇️ 數字越低越划算)\n"
        result_text += "----------------\n"
        
        bank_rates = []
        
        for index, row in target_df.iterrows():
            try:
                # 轉成字串並去除空白
                row_str = [str(x).strip() for x in row]
                print(row_str)
                # 假設第一欄是銀行名稱
                bank_name = row_str[0]
                print(bank_name)
                # 排除標題列 (有些標題列第一欄就是 '銀行')
                if "銀行" in bank_name: continue
                
                # 嘗試抓取匯率
                # FindRate 欄位通常是: 銀行(0), 現金買(1), 現金賣(2), 即期買(3), 即期賣(4)
                # 但有時候欄位會變，我們用 try-except 來容錯
                
                # 先試試看抓第 5 欄 (索引 4) - 即期賣出
                if len(row_str) > 4:
                    rate_str = row_str[4]
                else:
                    rate_str = '--'

                # 如果即期是 '--'，改抓第 3 欄 (索引 2) - 現金賣出
                if rate_str == '--' and len(row_str) > 2:
                    rate_str = row_str[2]

                if rate_str == '--': continue

                rate = float(rate_str)
                bank_rates.append((bank_name, rate))
                print(bank_rates)
            except Exception as e:
                continue

        # 排序與切分前 5 名
        bank_rates.sort(key=lambda x: x[1])
        top_5_banks = bank_rates[:5]

        if not top_5_banks:
            # 如果還是空的，回傳 Debug 資訊幫助我們除錯
            return f"抓取失敗。找到的表格欄位範例：{str(target_df.columns)}\n第一列資料：{str(target_df.iloc[0].values) if not target_df.empty else 'Empty'}"

        for i, (bank, rate) in enumerate(top_5_banks, 1):
            if i == 1: rank_icon = "🥇"
            elif i == 2: rank_icon = "🥈"
            elif i == 3: rank_icon = "🥉"
            else: rank_icon = f" {i}."

            result_text += f"{rank_icon} {bank}: {rate:.3f}\n"
            
        return result_text
        
    except Exception as e:
        return f"系統錯誤: {str(e)}"

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