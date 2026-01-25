
import google.generativeai as genai
from config import GEMINI_API_KEY

def get_ai_stock_analysis(symbol, stock_name, indicators):
    """
    使用 Gemini API 分析股票數據
    indicators: 由 indicator_service.get_latest_indicators() 產生的字典
    """
    if not GEMINI_API_KEY:
        return "❌ 尚未設定 Gemini API Key，無法進行 AI 分析。"

    if not indicators:
        return "❌ 無法取得技術指標數據，請稍後再試。"

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash') # 使用 Flash 模型速度快且免費額度高

        # 構建 Prompt
        prompt = f"""
        你是一位華爾街資深操盤手與技術分析專家。請根據以下數據分析 {stock_name} ({symbol}) 的走勢。
        
        【市場數據】
        - 現價: {indicators['close']:.2f}
        - 漲跌幅: {indicators['change_percent']:.2f}%
        - 成交量變化: {'量增' if indicators['volume_delta'] > 0 else '量縮'}

        【技術指標】
        - RSI (14): {indicators['rsi']:.2f} (強弱指標，>70超買, <30超賣)
        - MACD 柱狀圖: {indicators['macd_hist']:.2f} ({'多頭增強' if indicators['macd_hist'] > 0 else '空頭增強'})
        - 收盤 vs MA5: {'高於' if indicators['close'] > indicators['ma_5'] else '低於'} 短期均線
        - 收盤 vs MA20: {'高於' if indicators['close'] > indicators['ma_20'] else '低於'} 月線 (生命線)
        - 收盤 vs MA60: {'高於' if indicators['close'] > indicators['ma_60'] else '低於'} 季線
        - 布林通道位置: 目前在 {indicators['close']:.2f}，(上軌 {indicators['bb_upper']:.2f}, 下軌 {indicators['bb_lower']:.2f})

        【輸出要求】
        請用繁體中文，以條列式回答，語氣專業但白話：
        1. **市場情緒**: (看多/看空/盤整/中立)
        2. **關鍵價位**: (分析支撐位與壓力位)
        3. **趨勢分析**: (綜合均線、MACD 與 RSI 判斷目前趨勢)
        4. **操作建議**: (具體建議：進場、止損、獲利了結或觀望，並說明理由)

        請限制在 300 字以內，不要有過多的免責聲明，直接給出分析。
        """

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "⚠️ AI 分析暫時無法使用，請稍後再試。"
