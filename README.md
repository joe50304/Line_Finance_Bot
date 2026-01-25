# Line Finance Bot 📈

這是一個基於 Python Flask 與 Line Bot SDK 開發的金融助手機器人，整合了 Yahoo Finance 即時數據與 **Line Flex Message**，提供即時匯率、美股、台股查詢及 **AI 智能策略分析**功能。

![State-of-the-Art](https://img.shields.io/badge/State--of--the--Art-Yes-brightgreen)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 主要功能

### 1. � 即時匯率查詢
*   輸入幣別代碼（如 `USD`, `JPY`）即可獲得最新匯率與台灣銀行現鈔/即期報價。
*   輸入 `USD 1D` 或 `JPY 3M` 可查看匯率走勢圖。
*   支援查看幣別排行榜（`USD 列表`）。

### 2. 🇺🇸 美股資訊
*   輸入美股代號（如 `AAPL`, `TSLA`, `NVDA`）或指數（如 `^VIX`, `^DJI`）。
*   回傳即時股價、漲跌幅、本益比與 52 週高低點。

### 3. 🇹🇼 台股資訊 (含 AI 分析)
*   **基礎查詢**：輸入 `2330` 或 `台積電`，提供即時報價、五檔價量與三大法人資訊。
*   **技術圖表**：支援 `2330 日K`、`2330 週K`、`2330 交易量` 指令，回傳相應 K 線圖。
*   **🤖 AI 策略分析** (New!)：
    *   輸入 `2330 分析` 或 `TSLA 策略`。
    *   **核心功能**：
        1.  計算 RSI, MACD, 均線, 布林通道等 10+ 種技術指標。
        2.  **Gemini AI 解讀**：由 AI 擔任分析師，判斷多空趨勢。
        3.  **策略視覺化**：自動在 K 線圖上標註 **🟢支撐線** 與 **🔴壓力線**。

### 4. � 市場儀表板
*   輸入 `Hi`、`早安` 或 `盤前`，喚醒個人化儀表板。
*   一次瀏覽大盤指數 (TWII)、重要權值股與 VIX 恐慌指數。

## 🛠️ 安裝與部署

### 1. 環境設定
請確保已安裝 Python 3.9+，並設定虛擬環境：
```bash
conda create -n line_finance_bot python=3.12
conda activate line_finance_bot
pip install -r requirements.txt
```

### 2. 環境變數 (.env)
在 Render 或專案根目錄設定以下變數：
```ini
LINE_CHANNEL_ACCESS_TOKEN=你的LineToken
LINE_CHANNEL_SECRET=你的LineSecret
GEMINI_API_KEY=你的GoogleGeminiKey  <-- 新增此項以啟用 AI 功能
```

### 3. 本地執行
```bash
python app.py
```

### 4. 歷史回測 (進階)
驗證 AI 策略準確度，可執行內建回測腳本：
```bash
# 需先設定 GEMINI_API_KEY 環境變數
python backtest_strategy.py
```

## 📂 專案結構
```
.
├── app.py                  # 主程式 (Flask Server)
├── config.py               # 設定檔
├── services/
│   ├── ai_advisor_service.py # AI 分析 / Prompt Engineering
│   ├── chart_service.py      # 圖表繪製 (QuickChart/Yahoo)
│   ├── forex_service.py      # 匯率爬蟲
│   ├── indicator_service.py  # 技術指標計算 (Pandas TA)
│   └── stock_service.py      # 股價資訊抓取
└── backtest_strategy.py    # 策略回測腳本
```

## 🚀 部署平台
推薦使用 [Render](https://render.com/) 進行免費部署 (Web Service)。
Command: `gunicorn app:app`

---
Disclaimer: 本機器人提供之數據僅供參考，AI 分析建議不構成投資依據，投資請審慎評估。
