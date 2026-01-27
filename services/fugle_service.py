
import requests
from config import FUGLE_API_KEY

def get_realtime_quote(symbol):
    """
    從 Fugle API 取得個股即時報價
    API: https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}
    """
    if not FUGLE_API_KEY:
        print("[Debug] FUGLE_API_KEY not found.")
        return None

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
