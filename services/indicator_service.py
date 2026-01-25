
import pandas as pd
import pandas_ta as ta

def calculate_technical_indicators(df):
    """
    計算技術指標 (RSI, MACD, BBands, MA)
    df: 必須包含 Open, High, Low, Close, Volume 欄位
    """
    if df is None or df.empty:
        return None
    
    try:
        # 確保資料按時間排序
        df = df.sort_index()

        # 1. 移動平均線 (SMA) - 判斷均線排列
        df['SMA_5'] = ta.sma(df['Close'], length=5)
        df['SMA_10'] = ta.sma(df['Close'], length=10)
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_60'] = ta.sma(df['Close'], length=60)

        # 2. RSI 相對強弱指標 (14日) - 判斷超買超賣
        df['RSI'] = ta.rsi(df['Close'], length=14)

        # 3. MACD 指數平滑異同移動平均線 - 判斷趨勢強弱
        # macd() 回傳三個欄位: MACD_12_26_9, MACDh_12_26_9 (柱狀圖), MACDs_12_26_9 (訊號線)
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None:
             df = pd.concat([df, macd], axis=1)
        
        # 4. 布林通道 (Bollinger Bands) - 判斷波動與壓力支撐
        # bbands() 回傳: BBL (下軌), BBM (中軌), BBU (上軌), BBB (頻寬), BBP (位置)
        bbands = ta.bbands(df['Close'], length=20, std=2)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)

        return df
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return df

def get_latest_indicators(df):
    """
    取得最後一筆的指標數據，整理成字典供 AI 使用
    """
    try:
        df = calculate_technical_indicators(df)
        if df is None or df.empty: return None

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        # 整理 MACD 欄位名稱 (pandas_ta 的欄位名可能會有後綴)
        # 通常是 MACD_12_26_9, MACDh_12_26_9 (Histogram), MACDs_12_26_9 (Signal)
        # 為了安全，我們找含有 MACD 開頭的欄位
        macd_col = next((c for c in df.columns if c.startswith('MACD_')), None)
        hist_col = next((c for c in df.columns if c.startswith('MACDh_')), None)
        signal_col = next((c for c in df.columns if c.startswith('MACDs_')), None)
        
        return {
            "close": last['Close'],
            "change": last['Close'] - prev['Close'],
            "change_percent": (last['Close'] - prev['Close']) / prev['Close'] * 100,
            "rsi": last.get('RSI'),
            "macd": last.get(macd_col),
            "macd_hist": last.get(hist_col), # 正值代表多頭動能
            "macd_signal": last.get(signal_col),
            "ma_5": last.get('SMA_5'),
            "ma_20": last.get('SMA_20'),
            "ma_60": last.get('SMA_60'),
            "bb_upper": last.get(next((c for c in df.columns if c.startswith('BBU_')), None)),
            "bb_lower": last.get(next((c for c in df.columns if c.startswith('BBL_')), None)),
            "volume_delta": last['Volume'] - prev['Volume'] # 量縮或量增
        }
    except Exception as e:
        print(f"Error getting latest indicators: {e}")
        return None
