
import requests
import yfinance as yf
from cachetools import cached, TTLCache
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 股價相關 ---

def get_valid_stock_obj(symbol):
    def fetch(t):
        try: s = yf.Ticker(t); return s, s.fast_info
        except: return None, None
    for suffix in [".TW", ".TWO"]:
        s, i = fetch(symbol + suffix)
        try:
            if i and hasattr(i, 'last_price') and i.last_price: return s, i, suffix
        except: continue
    return None, None, None

@cached(TTLCache(maxsize=1, ttl=300))
def get_twse_stats():
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            stats = {}
            for item in data:
                code = item.get('Code')
                stats[code] = {
                    "PE": item.get('PEratio', '-'), 
                    "Yield": item.get('DividendYield', '-'),
                    "PB": item.get('PBratio', '-')
                }
            return stats
    except: pass
    return {}

@cached(TTLCache(maxsize=100, ttl=3600))
def get_stock_name(symbol):
    try:
        targets = [f"tse_{symbol}.tw", f"otc_{symbol}.tw", f"emg_{symbol}.tw"]
        query = "|".join(targets)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={query}&json=1&delay=0"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0'}
        r = requests.get(url, headers=headers, timeout=5, verify=False)
        
        if r.status_code == 200:
            data = r.json()
            if 'msgArray' in data:
                for item in data['msgArray']:
                    if item.get('c') == symbol and item.get('n'):
                        return item.get('n')
    except Exception as e:
        print(f"[Debug] Error getting stock name for {symbol}: {e}")
    
    return symbol

def get_stock_info(symbol):
    try:
        stock, info, suffix = get_valid_stock_obj(symbol)
        if not stock: return None
        
        extra_stats = {}
        if suffix == ".TW":
             all_stats = get_twse_stats()
             if symbol in all_stats: extra_stats = all_stats[symbol]

        stock_name = get_stock_name(symbol)
        if symbol == '7866' and stock_name == '7866':
            stock_name = "丹立"

        price = info.last_price
        prev_close = info.previous_close
        if prev_close is None: prev_close = price

        change = price - prev_close
        try: change_percent = (change / prev_close * 100) if prev_close else 0
        except: change_percent = 0
            

        if suffix in ['.TW', '.TWO']:
            from utils.common import calculate_twse_limit
            limit_up = calculate_twse_limit(prev_close, is_up=True)
            limit_down = calculate_twse_limit(prev_close, is_up=False)
        else:
            # 美股無漲跌幅限制 (或不同規則)，此處暫時保留原樣或設為 0
            limit_up = 0
            limit_down = 0

        return {
            "symbol": symbol, "name": stock_name,
            "price": price, 
            "change": change,
            "change_percent": change_percent,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "volume": info.last_volume, 
            "high": info.day_high, 
            "low": info.day_low,
            "avg_price": 0,
            "type": "上櫃" if suffix == ".TWO" else "上市",
            "PE": extra_stats.get("PE", "-"),
            "Yield": extra_stats.get("Yield", "-"),
            "PB": extra_stats.get("PB", "-")
        }
    except Exception as e:
        print(f"[Debug] Error getting stock info: {e}")
        return None

def get_us_stock_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
        
        if not price: return None
            
        change = price - prev_close if prev_close else 0
        change_percent = (change / prev_close * 100) if prev_close else 0
        
        return {
            "symbol": symbol,
            "name": info.get('shortName') or info.get('longName') or symbol,
            "price": price,
            "change": change,
            "change_percent": change_percent,
            "high": info.get('dayHigh') or info.get('regularMarketDayHigh') or 0,
            "low": info.get('dayLow') or info.get('regularMarketDayLow') or 0,
            "volume": info.get('volume') or info.get('regularMarketVolume') or 0,
            "market_cap": info.get('marketCap', 0),
            "pe_ratio": info.get('trailingPE', '-'),
            "week_52_high": info.get('fiftyTwoWeekHigh', '-'),
            "week_52_low": info.get('fiftyTwoWeekLow', '-')
        }
    except Exception as e:
        print(f"[Debug] Error getting US stock info for {symbol}: {e}")
        return None

def get_vix_data(days=5):
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period=f"{days+5}d")
        if hist.empty: return None
        hist = hist.tail(days)
        vix_data = []
        for index, row in hist.iterrows():
            vix_data.append({ "date": index.strftime('%Y-%m-%d'), "value": row['Close'] })
        return vix_data
    except Exception as e:
        print(f"[Debug] Error getting VIX data: {e}")
        return None

def generate_vix_report():
    vix_data = get_vix_data(5)
    if not vix_data: return "❌ 無法取得 VIX 資料"
    
    latest_vix = vix_data[-1]['value']
    if latest_vix < 15: sentiment = "😌 市場平靜"; sentiment_desc = "投資人情緒穩定"
    elif latest_vix < 20: sentiment = "📊 正常波動"; sentiment_desc = "市場處於正常狀態"
    elif latest_vix < 30: sentiment = "😰 市場緊張"; sentiment_desc = "投資人開始擔憂"
    else: sentiment = "😱 高度恐慌"; sentiment_desc = "市場處於恐慌狀態"
    
    report = f"📉 VIX 恐慌指數報告\n{'='*25}\n\n📅 過去 5 天 VIX 數值：\n\n"
    for item in vix_data: report += f"{item['date']}: {item['value']:.2f}\n"
    report += f"\n{'='*25}\n目前狀態：{sentiment}\n{sentiment_desc}\n\n💡 說明：\n• VIX < 15: 市場平靜\n• VIX 15-20: 正常波動\n• VIX 20-30: 市場緊張\n• VIX > 30: 高度恐慌"
    return report

def get_market_dashboard_data():
    tickers = ["^VIX", "^TWII", "0050.TW", "2330.TW"]
    name_map = {"^VIX": "VIX 恐慌", "^TWII": "加權指數", "0050.TW": "元大 0050", "2330.TW": "台積電"}
    results = []
    try:
        df = yf.download(tickers, period="5d", interval="1d", group_by='ticker', threads=True)
        for symbol in tickers:
            item_data = {
                "symbol": symbol, "name": name_map.get(symbol, symbol),
                "price": "-", "change": 0, "change_percent": 0, "color": "#333333", "sign": "",
                "action_text": symbol.replace(".TW", "")
            }
            try:
                if len(tickers) > 1: ticker_df = df[symbol]
                else: ticker_df = df
                ticker_df = ticker_df.dropna(subset=['Close'])
                if not ticker_df.empty:
                    last_row = ticker_df.iloc[-1]
                    price = last_row['Close']
                    if len(ticker_df) >= 2:
                        prev_row = ticker_df.iloc[-2]
                        prev_close = prev_row['Close']
                        change = price - prev_close
                        change_percent = (change / prev_close) * 100
                    else: change = 0; change_percent = 0
                    
                    color = "#eb4e3d" if change > 0 else "#27ba46" if change < 0 else "#333333"
                    sign = "+" if change > 0 else ""
                    item_data.update({
                        "price": f"{price:,.2f}",
                        "change": change,
                        "change_str": f"{sign}{change:.2f}",
                        "change_percent": f"{sign}{change_percent:.2f}%",
                        "color": color
                    })
            except Exception as e: print(f"[Debug] Error processing {symbol}: {e}")
            results.append(item_data)
        return results
    except Exception as e:
        print(f"[Debug] Error getting market dashboard data: {e}")
        return []

