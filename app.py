
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import urllib3

# Config & Utils
from config import (
    LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, TARGET_ID, 
    VALID_CURRENCIES, BOT_USER_ID
)
# Note: BOT_USER_ID cache is better handled in app scope or a singleton, 
# for now we keep the global variable logic here but initialize it via config logic or lazy load.

from utils.common import get_greeting
from utils.flex_templates import (
    generate_currency_flex_message, generate_help_message, 
    generate_currency_menu_flex, generate_dashboard_flex_message,
    generate_us_stock_flex_message, generate_stock_flex_message
)

# Services
from services.forex_service import get_taiwan_bank_rates, get_forex_info
from services.stock_service import (
    get_stock_info, get_us_stock_info, get_stock_name, 
    generate_vix_report, get_market_dashboard_data, get_valid_stock_obj
)
from services.chart_service import (
    generate_forex_chart_url_yf, generate_stock_chart_url_yf
)
from services.indicator_service import get_latest_indicators, calculate_technical_indicators
from services.ai_advisor_service import get_ai_stock_analysis
import yfinance as yf # Needed for fetching history for indicators
import pandas as pd


# 抑制 SSL 警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- Routes ---

@app.route("/", methods=['GET'])
def home(): return "Alive", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return 'OK'

@app.route("/push_forex", defaults={'currency': 'KRW'}, methods=['GET'])
@app.route("/push_forex/<currency>", methods=['GET'])
def push_forex(currency):
    """
    定時推送匯率報告 (可指定幣別, 預設 KRW)
    Usage: /push_forex (Default: KRW) or /push_forex/JPY
    """
    if not TARGET_ID: return "No Target ID", 500
    
    currency = currency.upper()
    if currency not in VALID_CURRENCIES:
        return f"Invalid Currency: {currency}. Supported: {', '.join(VALID_CURRENCIES)}", 400

    try:
        forex_report = get_taiwan_bank_rates(currency)
        
        # 處理報告回傳格式 (字串或列表)
        if isinstance(forex_report, list) and forex_report:
            report_str = f"📊 {currency} 匯率報告 (Top 10)\n{'-'*20}\n"
            for item in forex_report:
                report_str += f"{item['bank']}: {item['cash_selling']}\n"
        else:
            report_str = str(forex_report) if forex_report else "查無資料"

        message = f"{get_greeting()}！\n\n{report_str}"
        
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=message))
        return f"Forex Report Sent ({currency})", 200
    except Exception as e:
        print(f"Error pushing forex report: {e}")
        return str(e), 500

@app.route("/push_vix", methods=['GET'])
def push_vix():
    """定時推送 VIX 恐慌指數（晚上 18:00，由外部 cron job 觸發）"""
    if not TARGET_ID: return "No Target ID", 500
    try:
        vix_report = generate_vix_report()
        message = f"{get_greeting()}！\n\n{vix_report}"
        
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=message))
        return "VIX Report Sent", 200
    except Exception as e:
        print(f"Error pushing VIX report: {e}")
        return str(e), 500

# 保留舊的 /push_report 以便向後相容
@app.route("/push_report", methods=['GET'])
def push_report():
    """定時推送韓幣匯率與 VIX 恐慌指數報告（向後相容）"""
    if not TARGET_ID: return "No Target ID", 500
    try:
        krw_report = get_taiwan_bank_rates('KRW')
        # Here krw_report is list, need to convert to str for simple push
        krw_str = ""
        if isinstance(krw_report, list):
             for item in krw_report[:5]:
                 krw_str += f"{item['bank']}: {item['cash_selling']}\n"
        else: krw_str = str(krw_report)

        vix_report = generate_vix_report()
        full_report = f"{get_greeting()}！\n\n📊 韓幣匯率\n{krw_str}\n\n{vix_report}"
        
        line_bot_api.push_message(TARGET_ID, TextSendMessage(text=full_report))
        return "Report Sent (KRW + VIX)", 200
    except Exception as e:
        print(f"Error pushing report: {e}")
        return str(e), 500

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.upper().strip()
    
    # 0. 處理 Mentions (被標記) & 關鍵字問候
    is_greeting = False
    greetings = ["HI", "HELLO", "你好", "您好", "早安", "午安", "晚安", "嗨", "TEST", "測試"]
    msg_upper = msg.upper()
    
    # 判斷是否「真正」標記到了機器人
    is_mentioned_bot = False
    
    # 方法 A: 檢查 event 中的 mention 物件
    if hasattr(event.message, 'mention') and event.message.mention:
        global BOT_USER_ID
        if 'BOT_USER_ID' not in globals() or not BOT_USER_ID:
            try:
                bot_info = line_bot_api.get_bot_info()
                BOT_USER_ID = bot_info.user_id
            except:
                BOT_USER_ID = None
        
        if BOT_USER_ID:
            for mentionee in event.message.mention.mentionees:
                if mentionee.user_id == BOT_USER_ID:
                    is_mentioned_bot = True
                    break
    
    is_private_chat = (event.source.type == 'user')
    has_greeting_word = any(g in msg_upper for g in greetings)
    
    if is_mentioned_bot:
        is_greeting = True
    elif is_private_chat and has_greeting_word:
        is_greeting = True
    
    if not is_greeting and ("@" in msg and "BOT" in msg_upper): 
         is_greeting = True
         print(f"Fallback mention detected via text: {msg}")

    print(f"[Debug] Msg: {msg}, IsBotMention: {is_mentioned_bot}, IsPrivate: {is_private_chat}, HasGreeting: {has_greeting_word} -> IsGreeting: {is_greeting}")
    
    if is_greeting:
        user_id = event.source.user_id
        user_name = "朋友"
        try:
             if event.source.type == 'group':
                 profile = line_bot_api.get_group_member_profile(event.source.group_id, user_id)
             elif event.source.type == 'room':
                 profile = line_bot_api.get_room_member_profile(event.source.room_id, user_id)
             else:
                 profile = line_bot_api.get_profile(user_id)
             user_name = profile.display_name
        except: pass

        greeting_msg = get_greeting()
        market_data = get_market_dashboard_data()
        reply_flex = generate_dashboard_flex_message(greeting_msg, user_name, market_data)
        
        line_bot_api.reply_message(event.reply_token, reply_flex)
        return

    if msg in ['ID', '我的ID']:
        tid = event.source.group_id if event.source.type == 'group' else event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID: {tid}"))
        return

    if msg in ['HELP', 'MENU', '選單', '使用說明']:
        line_bot_api.reply_message(event.reply_token, generate_help_message())
        return

    if msg in ['幣別選單', '幣別列表', '匯率選單', '匯率列表']:
        line_bot_api.reply_message(event.reply_token, generate_currency_menu_flex())
        return

    # 1. 匯率查詢 (儀表板)
    if msg in VALID_CURRENCIES:
        forex_data = get_forex_info(msg)
        bank_report = get_taiwan_bank_rates(msg)
        
        if forex_data:
            flex_msg = generate_currency_flex_message(forex_data, bank_report)
            line_bot_api.reply_message(event.reply_token, flex_msg)
        else:
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
    if len(parts) == 2 and parts[0].isdigit():
        symbol = parts[0]
        cmd = parts[1]
        
        chart_url = None
        stock_name = get_stock_name(symbol)
        
        if cmd in ['即時', '即時走勢', '即時走勢圖']:
            chart_url = generate_stock_chart_url_yf(symbol, '1d', '5m', chart_type='line', stock_name=stock_name)
        elif cmd in ['日K', '日線']:
            chart_url = generate_stock_chart_url_yf(symbol, '1y', '1d', chart_type='candlestick', stock_name=stock_name)
        elif cmd in ['週K', '週線']:
            chart_url = generate_stock_chart_url_yf(symbol, '2y', '1wk', chart_type='candlestick', stock_name=stock_name)
        elif cmd in ['月K', '月線']:
            chart_url = generate_stock_chart_url_yf(symbol, '5y', '1mo', chart_type='candlestick', stock_name=stock_name)
        elif cmd in ['交易量', '近3日交易量']:
             chart_url = generate_stock_chart_url_yf(symbol, '1mo', '1d', chart_type='bar', stock_name=stock_name)

        if chart_url:
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=chart_url, preview_image_url=chart_url))
            return
        else:
            if cmd in ['即時', '日K', '週K', '月K', '交易量']:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 產生圖表失敗 ({cmd})"))
                return
        # If not handled above (e.g. '策略'), fall through to next logic
    
    # 5. 美股查詢（優先於台股，避免 AAPL 等被誤判為台股）
    # 偵測邏輯：純英文字母，1-5 個字元；或是以 ^ 開頭的指數 (e.g. ^VIX)
    is_us_stock = (msg.isalpha() and 1 <= len(msg) <= 5)
    is_index = (msg.startswith('^') and msg[1:].isalpha() and 2 <= len(msg) <= 6)
    
    if (is_us_stock or is_index) and msg.isupper():
        print(f"[US Stock Query] Attempting to fetch: {msg}")
        us_stock = get_us_stock_info(msg)
        if us_stock:
            line_bot_api.reply_message(event.reply_token, generate_us_stock_flex_message(us_stock))
            return
        else:
            print(f"[US Stock Query] No data found for: {msg}")
    
    # 6. 台股查詢（數字代號或混合代號，如 00981A）
    if msg.isascii() and msg.isalnum() and 4 <= len(msg) <= 6:
        if any(c.isdigit() for c in msg):
            print(f"[Taiwan Stock Query] Attempting to fetch: {msg}")
            stock = get_stock_info(msg)
            if stock:
                line_bot_api.reply_message(event.reply_token, generate_stock_flex_message(stock))
                return
            else:
                print(f"[Taiwan Stock Query] No data found for: {msg}")

    # 7. AI 智能分析 (股票代號 + 分析/策略)
    # e.g. "2330 分析", "AAPL 策略", "TSLA 分析"
    print(f"[Debug] Check AI Command: Parts={parts}, Len={len(parts)}")
    if len(parts) == 2 and parts[1] in ['分析', '策略', '建議']:
        symbol = parts[0]
        print(f"[Debug] AI Command Triggered: Symbol={symbol}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🤖 正在分析 {symbol} 的數據並諮詢 AI 顧問，請稍候... (約 3-5 秒)"))
        
        # 1. 取得歷史數據
        try:
            # 判斷是台股還是美股/全代號
            # 嘗試先用 helper 判斷
            s_obj, info, suffix = get_valid_stock_obj(symbol)
            if s_obj:
                full_symbol = symbol + suffix
            else:
                full_symbol = symbol # Assume US stock or valid ticker
            
            stock_name = get_stock_name(symbol)
            print(f"[Debug] Fetching history for {full_symbol}...")
            
            # 下載數據 (至少 60 天以計算 MA60, 3個月約60天太緊繃，改抓6個月)
            df = yf.download(full_symbol, period="6mo", interval="1d", progress=False)
            
            # Handle MultiIndex columns (yfinance v0.2+ / v1.1.0)
            if isinstance(df.columns, pd.MultiIndex):
                try:
                    # 如果只有一層 ticker，直接移除第二層 (Ticker層)
                    if len(df.columns.levels) > 1:
                         # 嘗試只取該 Ticker 的數據 (如果有指定 Ticker)
                         # 但通常下載單一股票時，直接 droplevel 即可
                         df.columns = df.columns.droplevel(1) 
                    else:
                         df.columns = df.columns.droplevel(1)
                except Exception as e:
                    print(f"[Debug] Flatten columns failed: {e}")
                    pass
            
            if df.empty:
                print(f"[Debug] History empty for {full_symbol}")
                line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ 找不到 {symbol} 的歷史數據，無法分析。"))
                return

            print(f"[Debug] History fetched. Rows={len(df)}")

            # 2. 計算技術指標
            indicators = get_latest_indicators(df)
            
            # 3. 呼叫 AI
            if indicators:
                print(f"[Debug] Indicators calculated. Calling AI...")
                ai_result = get_ai_stock_analysis(symbol, stock_name, indicators)
                print(f"[Debug] AI Result: {str(ai_result)[:50]}...")
                
                # Check format
                if isinstance(ai_result, dict):
                    analysis_text = ai_result.get('formatted_text', str(ai_result))
                    annotations = {
                        'support': ai_result.get('support_price'),
                        'resistance': ai_result.get('resistance_price')
                    }
                else:
                    analysis_text = str(ai_result)
                    annotations = None
                
                # 4. 同時產生一張 K 線圖作為輔助 (帶有分析線圖)
                print(f"[Debug] Generating Chart...")
                chart_url = generate_stock_chart_url_yf(
                    symbol, '6mo', '1d', 
                    chart_type='candlestick', 
                    stock_name=stock_name,
                    annotations=annotations
                )
                print(f"[Debug] Chart URL: {chart_url}")
                
                msgs = [TextSendMessage(text=f"🧠 AI 智能分析報告：\n\n{analysis_text}")]
                if chart_url:
                    msgs.insert(0, ImageSendMessage(original_content_url=chart_url, preview_image_url=chart_url))
                
                line_bot_api.push_message(event.source.user_id, msgs)
                print(f"[Debug] AI Report Sent.")
            else:
                print(f"[Debug] Indicator calculation failed.")
                line_bot_api.push_message(event.source.user_id, TextSendMessage(text="❌ 技術指標計算失敗 (數據不足)。"))
                
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ 分析過程中發生錯誤: {str(e)}"))
        return

if __name__ == "__main__":
    app.run()