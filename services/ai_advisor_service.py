import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
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
        
        # 嘗試使用不同的模型名稱 (優先使用 2.5 系列)
        model_names = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash', 'gemini-pro']
        model = None
        
        for name in model_names:
            try:
                # 測試模型是否可用 (此處僅建立物件，真正錯誤要在 generate_content 時才會觸發 404?)
                # 實際上 genai.GenerativeModel 不會立即檢查，所以我們直接用第一個，
                # 但為了保險，可以在這裡做一個小的 fallback 機制，或是直接指定最可能的那個。
                # 根據使用者回饋，直接鎖定 2.5 Pro 或 Flash。
                model = genai.GenerativeModel(name)
                break
            except: continue
            
        if not model: model = genai.GenerativeModel('gemini-2.5-flash')

        # 安全取得數值 (防止 None 導致 formatting error)
        def safe_get(key, default=0.0):
            val = indicators.get(key)
            return val if val is not None else default

        p_close = safe_get('close')
        p_change = safe_get('change_percent')
        p_vol_delta = indicators.get('volume_delta', 0)
        p_rsi = safe_get('rsi')
        p_macd_hist = safe_get('macd_hist')
        p_ma20 = safe_get('ma_20')
        p_bb_up = safe_get('bb_upper')
        p_bb_low = safe_get('bb_lower')

        # 構建 Prompt
        prompt = f"""
        你是一位華爾街資深操盤手。請根據以下數據分析 {stock_name} ({symbol}) 的走勢。
        
        【市場數據】
        - 現價: {p_close:.2f}
        - 漲跌幅: {p_change:.2f}%
        - 成交量變化: {'量增' if p_vol_delta > 0 else '量縮'}

        【技術指標】
        - RSI (14): {p_rsi:.2f} (強弱指標，>70超買, <30超賣)
        - MACD 柱狀圖: {p_macd_hist:.2f} ({'多頭增強' if p_macd_hist > 0 else '空頭增強'})
        - 收盤 vs MA20: {'高於' if p_close > p_ma20 else '低於'} 月線
        - 布林通道: 上軌 {p_bb_up:.2f}, 下軌 {p_bb_low:.2f}

        【輸出要求】
        請直接回傳一個合法的 JSON 物件 (不要有 markdown code block ` ```json `)，格式如下：
        {{
            "sentiment": "看多/看空/盤整",
            "support_price": <數值，分析出的下方支撐位，若無請填 null>,
            "resistance_price": <數值，分析出的上方壓力位，若無請填 null>,
            "action": "建議的操作 (如：拉回 1000 進場)",
            "reason": "簡短分析理由 (100字內)",
            "formatted_text": "完整分析報告 (條列式，包含市場情緒、關鍵價位、趨勢分析、操作建議，300字內)"
        }}
        """

        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # 清理可能存在的 Markdown 標記
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        import json
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"[Debug] JSON Parse Error: {text}")
            # Fallback to simple dict
            return {
                "sentiment": "未知",
                "formatted_text": text, # 回傳原始文字
                "support_price": None,
                "resistance_price": None
            }


    except ResourceExhausted as e:
        print(f"[Debug] Gemini Quota Exceeded: {e}")
        return {
            "formatted_text": "⚠️ Gemini AI 額度已達上限 (429 Too Many Requests)\n\nGoogle 免費版 API 有每分鐘請求限制 (RPM)。請稍候 60 秒後再試一次。\n\n如持續遇到此問題，建議稍晚再試。造成不便請見諒！🙇",
            "sentiment": "N/A",
            "support_price": None,
            "resistance_price": None
        }
    except Exception as e:
        print(f"[Debug] Gemini API Error: {e}")
        return "⚠️ AI 分析暫時無法使用 (API Error)，請稍後再試。"
