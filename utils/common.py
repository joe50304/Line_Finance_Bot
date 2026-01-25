
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
