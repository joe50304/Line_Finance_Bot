
import pytz
from datetime import datetime

# --- 問候語 ---
def get_greeting():
    try:
        tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(tz)
        hour = now.hour
        if 5 <= hour < 12: return "早上好 🌞"
        elif 12 <= hour < 18: return "下午好 🍱"
        elif 18 <= hour < 24: return "晚安 🌙"
        else: return "凌晨好 🌞"
    except:
        return "你好 🤖"

# --- 台股工具 ---

from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

def get_twse_tick(price):
    """取得台股股價的最小升降單位 (Tick)"""
    if price < 10: return Decimal('0.01')
    elif price < 50: return Decimal('0.05')
    elif price < 100: return Decimal('0.1')
    elif price < 500: return Decimal('0.5')
    elif price < 1000: return Decimal('1.0')
    else: return Decimal('5.0')

def calculate_twse_limit(prev_close, is_up=True):
    """
    計算台股漲跌停價 (10% 限制)
    規則：前一日收盤價 * 1.10 (或 0.90)，並依照 Tick 規則無條件捨去/進位
    """
    if not prev_close: return 0.0
    
    d_prev = Decimal(str(prev_close))
    factor = Decimal('1.10') if is_up else Decimal('0.90')
    raw_target = d_prev * factor
    
    # 取得目標價位的 Tick (注意：Tick 取決於價格區間)
    # 但在邊界時，應該用哪個？通常是用 raw_target 所在的區間
    tick = get_twse_tick(float(raw_target))
    
    if is_up:
        # 漲停：不可超過 +10%，故無條件捨去至 Tick
        # ex: 142 * 1.1 = 156.2. Tick 0.5. -> 156.0
        rounded = (raw_target // tick) * tick
    else:
        # 跌停：不可超過 -10%，故無條件進位至 Tick (因為是價位，要取較高的值才不會跌破 10%)
        # ex: 142 * 0.9 = 127.8. Tick 0.5. -> 128.0
        # 數學上：找大於等於 raw_target 的最小 Tick 倍數
        # 使用 ceiling
        rounded = raw_target / tick
        rounded = rounded.to_integral_value(rounding=ROUND_CEILING) * tick

    return float(rounded)
