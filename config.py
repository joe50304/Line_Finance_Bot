
import os

# --- 設定區 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TARGET_ID = os.environ.get('MY_USER_ID', '')
BOT_USER_ID = None

# --- 支援的幣別代碼清單 ---
VALID_CURRENCIES = [
    "USD", "HKD", "GBP", "AUD", "CAD", "SGD", "CHF", "JPY", "ZAR", "SEK", "NZD", 
    "THB", "PHP", "IDR", "EUR", "KRW", "VND", "MYR", "CNY", "INR", "DKK", "MOP", 
    "MXN", "TRY"
]
