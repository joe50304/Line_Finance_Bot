
import requests
import yfinance as yf
from utils.common import get_greeting # Optional if used or not

def generate_forex_chart_url_yf(currency_code, period="1d", interval="15m"):
    """
    產生匯率走勢圖
    """
    try:
        symbol = f"{currency_code}TWD=X"
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        # Fallback 1: 1d 沒資料 -> 抓 5d
        if data.empty and period == '1d':
            period = '5d'
            interval = '60m'
            data = ticker.history(period=period, interval=interval)

        # Fallback 2: 1y 沒資料 (偶爾發生) -> 嘗試抓 6mo
        if data.empty and period == '1y':
            period = '6mo'
            data = ticker.history(period=period, interval=interval)

        if data.empty:
            return None
            
        dates = []
        prices = []
        
        # 格式化 X 軸日期
        for index, row in data.iterrows():
            if period == '1d':
                dt_str = index.strftime('%H:%M')
            elif period == '5d':
                dt_str = index.strftime('%m/%d %H')
            else:
                dt_str = index.strftime('%Y-%m-%d')
                
            dates.append(dt_str)
            prices.append(row['Close'])

        # 縮減資料點 (QuickChart URL 長度限制)
        if len(dates) > 60:
            step = len(dates) // 60 + 1
            dates = dates[::step]
            prices = prices[::step]

        # QuickChart 設定
        chart_config = {
            "type": "line",
            "data": {
                "labels": dates,
                "datasets": [{
                    "label": f"{currency_code}/TWD ({period})",
                    "data": prices,
                    "borderColor": "#1DB446",
                    "backgroundColor": "rgba(29, 180, 70, 0.1)",
                    "fill": True,
                    "pointRadius": 0,
                    "borderWidth": 2,
                    "lineTension": 0.1
                }]
            },
            "options": {
                "title": {"display": True, "text": f"{currency_code} 匯率走勢 ({period})"},
                "legend": {"display": False},
                "scales": {
                    "yAxes": [{"ticks": {"beginAtZero": False}}],
                    "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 6}}] 
                }
            }
        }
        
        url = "https://quickchart.io/chart/create"
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 600,
            "backgroundColor": "white",
            "version": "2.9.4"
        }
        
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            return response.json().get('url')
        else:
            return None
            
    except Exception as e:
        print(f"Chart Error: {e}")
        return None

def generate_stock_chart_url_yf(symbol, period="1d", interval="15m", chart_type="line", stock_name=None, annotations=None):
    """
    產生台股走勢圖 (自動判斷上市/上櫃)
    chart_type: 'line' (折線圖), 'candlestick' (K線圖), 'bar' (交易量)
    annotations: dict, e.g. {'support': 1000, 'resistance': 1100}
    """
    # Import locally to avoid circular import if stock_service imports this
    # But here we need get_stock_name...
    # Better: Pass full stock name as argument from controller
    # Or import stock_service inside function
    from services.stock_service import get_stock_name, get_valid_stock_obj

    # 如果沒有提供中文名稱，嘗試取得
    if not stock_name:
        stock_name = get_stock_name(symbol)
        if stock_name == symbol:
            display_name = symbol
        else:
            display_name = f"{symbol} {stock_name}"
    else:
        display_name = f"{symbol} {stock_name}"
    try:
        # 判斷是上市還是上櫃
        stock, info, suffix = get_valid_stock_obj(symbol)
        if not stock: return None
        
        full_symbol = symbol + suffix
        ticker = yf.Ticker(full_symbol)
        
        data = ticker.history(period=period, interval=interval)
        
        if data.empty: return None

        version = '2.9.4' # default
        
        # Build Annotation Plugin Config
        annotation_config = {}
        if annotations:
            annotations_list = []
            if annotations.get('support'):
                annotations_list.append({
                    "type": "line",
                    "mode": "horizontal",
                    "scaleID": "y-axis-0",
                    "value": annotations['support'],
                    "borderColor": "green",
                    "borderWidth": 2,
                    "borderDash": [5, 5],
                    "label": {
                        "content": f"Support: {annotations['support']}",
                        "enabled": True,
                        "position": "left",
                        "backgroundColor": "rgba(0,0,0,0.5)"
                    }
                })
            if annotations.get('resistance'):
                annotations_list.append({
                    "type": "line",
                    "mode": "horizontal",
                    "scaleID": "y-axis-0",
                    "value": annotations['resistance'],
                    "borderColor": "red",
                    "borderWidth": 2,
                    "borderDash": [5, 5],
                    "label": {
                        "content": f"Resist: {annotations['resistance']}",
                        "enabled": True,
                        "position": "right",
                        "backgroundColor": "rgba(0,0,0,0.5)"
                    }
                })
            
            if annotations_list:
                annotation_config = {
                    "annotations": annotations_list
                }


        # ----------------------------
        # 1. 折線圖 (Line Chart) v2
        # ----------------------------
        if chart_type == 'line':
            dates = []
            prices = []
            
            # Intraday (1d/5d) logic
            for index, row in data.iterrows():
                if period == '1d' or interval in ['1m','2m','5m','15m','30m']:
                    dt_str = index.strftime('%H:%M')
                else:
                    dt_str = index.strftime('%m/%d')
                    
                dates.append(dt_str)
                prices.append(row['Close'])

            # Sampling
            if len(dates) > 60:
                step = len(dates) // 60 + 1
                dates = dates[::step]
                prices = prices[::step]

            color = "#eb4e3d" if prices[-1] >= prices[0] else "#27ba46"
            
            chart_config = {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [{
                        "label": f"{symbol}",
                        "data": prices,
                        "borderColor": color,
                        "backgroundColor": f"{color}1A",
                        "fill": True,
                        "pointRadius": 0,
                        "borderWidth": 2,
                        "lineTension": 0.1
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{display_name} 走勢"},
                    "legend": {"display": False},
                    "annotation": annotation_config, # v2 annotation
                    "scales": {
                        "yAxes": [{"id": "y-axis-0", "ticks": {"beginAtZero": False}}],
                        "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 6}}] 
                    }
                }
            }

        # ----------------------------
        # 2. K線圖 (Candlestick) v3
        # ----------------------------
        elif chart_type == 'candlestick':
            # Use Chart.js v3 for Candlestick (Better support in QuickChart)
            # Annotation logic for v3 is slighty different structure, usually inside plugins
            version = '3'
            
            # Limit data points for clean rendering
            if len(data) > 60:
                data = data.tail(60)

            labels = []
            ohlc_data = []
            
            for index, row in data.iterrows():
                date_str = index.strftime('%Y-%m-%d')
                labels.append(date_str)
                ohlc_data.append({
                    "x": date_str,
                    "o": float(row['Open']),
                    "h": float(row['High']),
                    "l": float(row['Low']),
                    "c": float(row['Close'])
                })
                
            # Adjust annotation structure for v3
            if annotations:
                # v3 annotations are under plugins.annotation.annotations
                # which can be an object or array. QuickChart supports array.
                v3_annotations = {} 
                # Re-map scaleID 'y-axis-0' to 'y' for v3
                for i, ann in enumerate(annotation_config.get('annotations', [])):
                     ann['scaleID'] = 'y'
                     # v3 label config is different, simplistic approach for now
                     # QuickChart often handles v2 compat, but explicit v3 is better
                     v3_annotations[f"line{i}"] = ann

                annotation_config = { "annotations": v3_annotations }

            
            chart_config = {
                "type": "candlestick",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": f"{symbol}", 
                        "data": ohlc_data,
                        # Chart.js v3 financial colors
                        "color": {
                            "up": "#eb4e3d",
                            "down": "#27ba46",
                            "unchanged": "#999"
                        },
                         "borderColor": {
                            "up": "#eb4e3d",
                            "down": "#27ba46",
                            "unchanged": "#999"
                        }
                    }]
                },
                "options": {
                    "plugins": {
                        "title": { "display": True, "text": f"{display_name} K線圖 ({'日K' if 'd' in interval else '週K' if 'wk' in interval else '月K'})" },
                        "legend": { "display": False },
                        "annotation": annotation_config
                    },
                    "scales": {
                        "x": {
                            "type": "category", # important for v3 candlestick with string labels
                            "offset": True,
                            "ticks": { "maxTicksLimit": 6 }
                        },
                        "y": {
                            "ticks": { "beginAtZero": False }
                        }
                    }
                }
            }


        # ----------------------------
        # 3. 交易量圖 (Volume Bar Chart) v2 or v3
        # ----------------------------
        elif chart_type == 'bar':
             # Let's keep v2 for bar chart as it works reliably
             version = '2.9.4'
             
             if len(data) > 60:
                 step = len(data) // 60 + 1
                 data = data.iloc[::step]
            
             dates = []
             volumes = []
             colors = []
             
             for index, row in data.iterrows():
                 dt_str = index.strftime('%m/%d')
                 dates.append(dt_str)
                 volumes.append(int(row['Volume']))
                 
                 # color based on price change if possible, or just blue
                 if row['Close'] >= row['Open']:
                     colors.append('#eb4e3d')
                 else:
                     colors.append('#27ba46')

             chart_config = {
                "type": "bar",
                "data": {
                    "labels": dates,
                    "datasets": [{
                        "label": "Volume",
                        "data": volumes,
                        "backgroundColor": colors
                    }]
                },
                "options": {
                    "title": {"display": True, "text": f"{display_name} 交易量 ({period})"},
                    "legend": {"display": False},
                    "scales": {
                        "yAxes": [{"ticks": {"beginAtZero": True}}],
                        "xAxes": [{"ticks": {"autoSkip": True, "maxTicksLimit": 6}}]
                    }
                }
             }

        # 發送 Request
        url = "https://quickchart.io/chart/create"
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 600,
            "backgroundColor": "white",
            "version": version
        }
        
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            return response.json().get('url')
        else:
            print(f"QuickChart Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Stock Chart Error: {e}")
        return None
