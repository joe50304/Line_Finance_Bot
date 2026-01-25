
import requests
import pandas as pd
import io
import yfinance as yf
from cachetools import cached, TTLCache

# Cache Settings
rate_cache = TTLCache(maxsize=30, ttl=300)

@cached(rate_cache)
def get_taiwan_bank_rates(currency_code="HKD"):
    """
    從比率網 (FindRate) 抓取台灣各家銀行的「現鈔賣出」匯率
    """
    try:
        url = f"https://www.findrate.tw/{currency_code}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8' 
        
        # 使用 io.StringIO 包裝
        html_buffer = io.StringIO(response.text)
        dfs = pd.read_html(html_buffer)
        
        target_df = None
        for df in dfs:
            cols_str = str(df.columns)
            if "現鈔賣出" in cols_str: 
                 target_df = df
                 break
        
        if target_df is None:
            for df in dfs:
                if len(df.columns) >= 5 and "銀行" in str(df.columns):
                    target_df = df
                    break
        
        if target_df is None:
            return f"找不到 {currency_code} 的匯率表格，可能該網站未提供。"

        bank_rates = []
        
        for i in range(len(target_df)):
            try:
                row = target_df.iloc[i]
                bank_name = str(row.iloc[0]).strip()
                cash_selling = str(row.iloc[2]).strip()
                spot_selling = str(row.iloc[4]).strip()
                update_time = str(row.iloc[5]).strip()

                if bank_name in ["銀行名稱", "銀行", "幣別"]: continue
                if cash_selling == '--' and spot_selling == '--': continue
                if len(bank_name) > 20: continue

                rate_val = 9999.0
                try: rate_val = float(cash_selling)
                except: 
                    try: rate_val = float(spot_selling)
                    except: pass
                
                bank_rates.append({
                    "bank": bank_name,
                    "cash_selling": cash_selling,
                    "spot_selling": spot_selling,
                    "rate_sort": rate_val,
                    "time": update_time
                })
            except: continue

        bank_rates.sort(key=lambda x: x['rate_sort'])
        return bank_rates[:10]
        
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []
        
    except Exception as e:
        return f"查詢失敗: {str(e)[:100]}..."

def get_forex_info(currency_code):
    try:
        symbol = f"{currency_code}TWD=X"
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        
        if not hasattr(info, 'last_price') or info.last_price is None:
            return None

        current_price = info.last_price
        prev_close = info.previous_close
        
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        return {
            "currency": currency_code,
            "price": current_price,
            "change": change,
            "change_percent": change_percent
        }
    except Exception as e:
        print(f"Forex Info Error: {e}")
        return None

