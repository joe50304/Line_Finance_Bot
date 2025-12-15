# 匯率快報機器人 (LINE Exchange Rate Bot) 🤖

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.x-green.svg)
![LINE API](https://img.shields.io/badge/LINE_Messaging_API-SDK-success)
![Render](https://img.shields.io/badge/Deployed_on-Render-informational)

這是一個基於 Python Flask 開發的 LINE 機器人，專門用於查詢 **台灣各家銀行** 的即時外幣匯率。
它會爬取 [FindRate 比率網](https://www.findrate.tw/) 的資料，並針對「現鈔賣出」匯率進行排序，幫您找出換匯最划算的銀行前五名。

## ✨ 主要功能 (Features)

* **即時匯率查詢**：輸入幣別代碼（如 `USD`, `JPY`, `HKD`），立即回傳台灣各銀行最優匯率前 5 名。
* **智慧過濾**：
    * 針對「現鈔賣出」匯率進行比較（出國換錢最實用）。
    * 自動過濾無報價的銀行。
    * 支援 20+ 種常見幣別（白名單機制，避免誤觸）。
* **定時推播 (Cron Job)**：
    * 每天固定時間（如早上 8:00）主動推播匯率報告到指定群組或個人。
    * **動態問候語**：依據台灣時間自動判斷並傳送「早安/午安/晚安」。
* **群組友善**：在群組中只有輸入特定指令才會觸發，平時保持安靜。
* **ID 查詢助手**：輸入 `ID` 或 `我的ID`，機器人會告知當前群組或個人的 ID，方便設定推播目標。

## 🛠️ 技術棧 (Tech Stack)

* **語言**：Python 3
* **框架**：Flask (Web Server)
* **爬蟲**：Pandas, Requests, lxml (解析 HTML 表格)
* **SDK**：line-bot-sdk
* **部署**：Render (Web Service)
* **排程**：Cron-job.org (觸發定時推播與喚醒)

## 🚀 支援幣別 (Supported Currencies)

目前支援查詢以下幣別：
`USD`, `HKD`, `GBP`, `AUD`, `CAD`, `SGD`, `CHF`, `JPY`, `ZAR`, `SEK`, `NZD`, `THB`, `PHP`, `IDR`, `EUR`, `KRW`, `VND`, `MYR`, `CNY`, `INR`, `DKK`, `MOP`, `MXN`, `TRY`

## ⚙️ 安裝與執行 (Installation)

### 1. 複製專案
```bash
git clone https://github.com/joe50304/Line_Finance_Bot.git
cd Line_Finance_Bot
```

### 2.進行Library安裝
```bash
pip install -r requirements.txt
```

### 3.運行此程式
```bash
python app.py
```

