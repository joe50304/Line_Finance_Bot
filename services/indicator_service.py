import pandas as pd
import numpy as np

def calculate_technical_indicators(df):
    """
    計算技術指標 (RSI, MACD, BBands, MA)
    改用純 Pandas 實作，移除 pandas_ta 與 numba 依賴，以節省記憶體並避免 Render OOM。
    """
    if df is None or df.empty:
        return None
    
    try:
        # 確保資料按時間排序
        df = df.sort_index()
        close = df['Close']

        # 1. 移動平均線 (SMA)
        df['SMA_5'] = close.rolling(window=5).mean()
        df['SMA_10'] = close.rolling(window=10).mean()
        df['SMA_20'] = close.rolling(window=20).mean()
        df['SMA_60'] = close.rolling(window=60).mean()

        # 2. RSI 相對強弱指標 (14日)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        # 此處使用簡單移動平均 (SMA) 版本的 RSI 公式，與常見的 Wilder's Smoothing 略有不同但足夠近似
        # 為求精確，改用 EMA 模擬 Wilder's Smoothing
        # gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        # loss = -delta.where(delta < 0, 0).ewm(alpha=1/14, adjust=False).mean()
        # 目前使用簡單版即可避免依賴
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. MACD (12, 26, 9)
        # MACD = EMA(12) - EMA(26)
        # Signal = EMA(9) of MACD
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line
        
        df['MACD_line'] = macd_line
        df['MACD_signal'] = signal_line
        df['MACD_hist'] = macd_hist # 柱狀圖

        # 4. 布林通道 (20, 2)
        # 中軌 = SMA(20)
        # 上軌 = SMA(20) + 2 * std(20)
        # 下軌 = SMA(20) - 2 * std(20)
        ma20 = df['SMA_20']
        std20 = close.rolling(window=20).std()
        df['BBU_20_2.0'] = ma20 + (std20 * 2)
        df['BBL_20_2.0'] = ma20 - (std20 * 2)

        return df
    except Exception as e:
        print(f"[Debug] Error calculating indicators: {e}")
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
        
        return {
            "close": last['Close'],
            "change": last['Close'] - prev['Close'],
            "change_percent": (last['Close'] - prev['Close']) / prev['Close'] * 100,
            "rsi": last.get('RSI'),
            "macd": last.get('MACD_line'),
            "macd_hist": last.get('MACD_hist'), # 正值代表多頭動能
            "macd_signal": last.get('MACD_signal'),
            "ma_5": last.get('SMA_5'),
            "ma_20": last.get('SMA_20'),
            "ma_60": last.get('SMA_60'),
            "bb_upper": last.get('BBU_20_2.0'),
            "bb_lower": last.get('BBL_20_2.0'),
            "volume_delta": last['Volume'] - prev['Volume'] # 量縮或量增
        }
    except Exception as e:
        print(f"[Debug] Error getting latest indicators: {e}")
        return None
