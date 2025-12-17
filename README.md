# 金融快報機器人 (Line Finance Bot) 🤖

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.x-green.svg)
![LINE API](https://img.shields.io/badge/LINE_Messaging_API-SDK-success)
![Render](https://img.shields.io/badge/Deployed_on-Render-informational)

這是一個全方位的金融資訊 LINE 機器人，整合了 **外幣匯率** 與 **台灣股市** 的即時資訊查詢功能。
不僅能幫您找出匯率最划算的銀行，還能提供台股即時報價、技術分析圖表（K線、成交量），是您投資理財的好幫手！

## ✨ 主要功能 (Features)

### 1. 🌏 加強版匯率查詢 (Forex)
* **即時找匯差**：輸入幣別代碼（如 `USD`, `JPY`），立即回傳台灣各銀行「現鈔賣出」最優匯率前 5 名。
* **歷史走勢圖**：
    * 輸入 `USD圖`、`日幣走勢`，機器人會繪製近期的匯率折線圖，幫您判斷買點。
    * **智慧過濾**：若查無資料或指令不明確，機器人會保持安靜，不打擾對話。

### 2. 📈 台股即時達人 (Taiwan Stocks)
* **即時報價看板**：
    * 輸入股票代號（如 `2330`, `0050`），回傳美觀的 Flex Message 看板。
    * 包含：現價、漲跌幅、漲跌停價、當日最高/低、成交量等完整資訊。
* **專業圖表分析**：
    * **即時走勢**：`2330 即時` -> 顯示當日股價走勢圖（若未開盤會顯示前一日）。
    * **K 線圖**：`2330 日K` -> 顯示日/週/月 K 線圖（Candlestick），支援紅漲綠跌顯示。
    * **成交量**：`2330 交易量` -> 顯示近三日成交量變化。
* **防擾機制**：
    * 聊天中提到「2330」會觸發，但若輸入「2330 觀察中」等非指令語句，機器人會自動忽略。

### 3. 💬 互動與貼心功能
* **定時推播**：支援 Cron Job 定時發送匯率/股價報告。
* **專屬問候**：在群組中 Tag 機器人 (`@Bot`)，它會根據現在時間親切地向您（大帥哥/美女）問好！
* **ID 查詢**：輸入 `ID` 或 `我的ID`，快速查詢群組或個人 User ID。

## � 指令列表 (Commands)

| 功能類別 | 指令範例 | 說明 |
| :--- | :--- | :--- |
| **匯率查詢** | `USD`, `JPY`, `歐元` | 查詢該幣別最佳換匯銀行 |
| **匯率走勢** | `USD圖`, `日幣走勢` | 顯示歷史匯率折線圖 |
| **台股報價** | `2330`, `0050` | 呼叫個股即時資訊卡片 |
| **台股圖表** | `2330 即時` | 顯示即時走勢圖 |
| **台股圖表** | `2330 日K`, `2330 週K` | 顯示 K 線圖 |
| **台股圖表** | `2330 交易量` | 顯示近三日成交量 |
| **問候** | `@Bot` (Tag機器人) | 機器人向您問好 |
| **工具** | `ID` | 查詢 User ID |

## 🚀 支援幣別 (Supported Currencies)

目前支援查詢以下幣別 (FindRate 來源)：
`USD`, `HKD`, `GBP`, `AUD`, `CAD`, `SGD`, `CHF`, `JPY`, `ZAR`, `SEK`, `NZD`, `THB`, `PHP`, `IDR`, `EUR`, `KRW`, `VND`, `MYR`, `CNY`, `INR`, `DKK`, `MOP`, `MXN`, `TRY`

## 🛠️ 技術棧 (Tech Stack)

* **語言**：Python 3
* **框架**：Flask (Web Server)
* **資料來源**：
    * 匯率：[FindRate 比率網](https://www.findrate.tw/) (爬蟲)
    * 台股：`yfinance` API
* **圖表繪製**：`QuickChart.io` (Chart.js 渲染引擎)
* **SDK**：line-bot-sdk
* **部署**：Render

## ⚙️ 安裝與執行 (Installation)

### 1. 複製專案
```bash
git clone https://github.com/joe50304/Line_Finance_Bot.git
cd Line_Finance_Bot
```

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 設定環境變數
請確保設定以下環境變數 (或是 .env 檔案)：
* `LINE_CHANNEL_ACCESS_TOKEN`
* `LINE_CHANNEL_SECRET`

### 4. 運行程式
```bash
python app.py
```
