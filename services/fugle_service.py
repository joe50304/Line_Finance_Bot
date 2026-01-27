
import requests
import time
from config import FUGLE_API_KEY

# Rate Limiting: 60 requests per minute
_req_count = 0
_window_start = 0

def get_realtime_quote(symbol):
    """
    從 Fugle API 取得個股即時報價 (含 Rate Limiting)
    API: https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}
    """
    global _req_count, _window_start

    if not FUGLE_API_KEY:
        # print("[Debug] FUGLE_API_KEY not found.") # Reduce noise
        return None

    # Check Rate Limit
    now = time.time()
    if now - _window_start > 60:
        # Reset window
        _window_start = now
        _req_count = 0
    
    if _req_count >= 58: # Buffer: 設定 58 讓它稍微保守一點 (官方限 60)
        print(f"[Warn] Fugle API Rate Limit Reached ({_req_count}/60). Fallback to Yahoo.")
        return None

    _req_count += 1

    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
        headers = {
            "X-API-KEY": FUGLE_API_KEY
        }
        r = requests.get(url, headers=headers, timeout=5)
        
        if r.status_code == 200:
            data = r.json()
            # Fugle API Response Structure:
            # {
            #   "date": "2024-01-27",
            #   "type": "EQUITY",
            #   "exchange": "TWSE",
            #   "market": "TSE",
            #   "symbol": "2330",
            #   "name": "台積電",
            #   "referencePrice": 644,
            #   "previousClose": 644,
            #   ...
            #   "total": {
            #     "tradeValue": 12345678,
            #     "tradeVolume": 12345, # Shares
            #     "tradeVolumeAtBid": ...
            #   },
            #   "lastTrade": {
            #     "price": 648,
            #     "size": 1,
            #     "time": "13:30:00"
            #   },
            #   "prices": [ ... ],
            #   ...
            # }
            
            return data
        else:
            print(f"[Debug] Fugle API Error: {r.status_code} - {r.text}")
            return None

    except Exception as e:
        print(f"[Debug] Fugle Service Error: {e}")
        return None
