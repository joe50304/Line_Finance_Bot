
from linebot.models import (
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, ButtonComponent,
    MessageAction, SeparatorComponent, ImageSendMessage, TextSendMessage, FillerComponent
)

def generate_currency_flex_message(forex_data, bank_report_text):
    c_code = forex_data['currency']
    price = forex_data['price']
    change = forex_data['change']
    percent = forex_data['change_percent']
    
    if change > 0: color = "#eb4e3d"; sign = "+"
    elif change < 0: color = "#27ba46"; sign = ""
    else: color = "#333333"; sign = ""

    # Build Top 5 Banks Rows
    bank_rows = []
    # Header
    bank_rows.append(
        BoxComponent(
            layout='horizontal',
            contents=[
                TextComponent(text="銀行", size='xxs', color='#aaaaaa', flex=3),
                TextComponent(text="現鈔賣出", size='xxs', color='#aaaaaa', align='end', flex=2),
                TextComponent(text="即期賣出", size='xxs', color='#aaaaaa', align='end', flex=2)
            ]
        )
    )
    
    # Data Rows
    if isinstance(bank_report_text, list):
        for i, b in enumerate(bank_report_text[:5]): # Top 5
            row_color = "#333333"
            if i == 0: row_color = "#eb4e3d" # Top 1 highlight
            
            bank_rows.append(
                BoxComponent(
                    layout='horizontal', margin='xs',
                    contents=[
                        TextComponent(text=b['bank'], size='xs', color=row_color, flex=3, weight='bold' if i==0 else 'regular'),
                        TextComponent(text=b['cash_selling'], size='xs', color=row_color, align='end', flex=2),
                        TextComponent(text=b['spot_selling'], size='xs', color='#555555', align='end', flex=2)
                    ]
                )
            )
    else:
        # Fallback if error string
        bank_rows.append(TextComponent(text=str(bank_report_text), size='xs', color='#ff0000'))


    return FlexSendMessage(
        alt_text=f"{c_code} 匯率快報",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{c_code}/TWD 匯率", weight='bold', size='xl', color='#555555'),
                    TextComponent(text="台灣時間即時行情 (Yahoo)", size='xxs', color='#aaaaaa'),
                    BoxComponent(
                        layout='baseline', margin='md',
                        contents=[
                            TextComponent(text=f"{price:.4f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{change:.4f} ({sign}{percent:.2f}%)", size='xs', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    TextComponent(text="🇹🇼 台灣銀行最佳匯率 (Top 5)", size='sm', weight='bold', color='#555555', margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='md', spacing='xs',
                        contents=bank_rows
                    ),
                    SeparatorComponent(margin='lg'),
                    TextComponent(text="歷史走勢圖:", size='xs', color='#aaaaaa', margin='md'),
                    BoxComponent(
                        layout='horizontal', margin='sm', spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1日走勢', text=f'{c_code} 1D')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='5日走勢', text=f'{c_code} 5D'))
                        ]
                    ),
                    BoxComponent(
                        layout='horizontal', margin='sm', spacing='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1月走勢', text=f'{c_code} 1M')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='1年走勢', text=f'{c_code} 1Y'))
                        ]
                    ),
                    ButtonComponent(style='link', height='sm', action=MessageAction(label='查看完整銀行比價', text=f'{c_code} 列表'))
                ]
            )
        )
    )

def generate_help_message():
    """產生整合式功能說明選單"""
    return FlexSendMessage(
        alt_text="功能選單",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text="🤖 金融助手功能導覽", weight='bold', size='lg', color='#1DB446'),
                    TextComponent(text="點擊下方按鈕或輸入指令試試看！", size='xs', color='#aaaaaa', margin='xs'),
                    
                    SeparatorComponent(margin='md'),
                    
                    # 1. 外匯專區
                    TextComponent(text="🌏 外匯查詢", weight='bold', size='sm', color='#555555', margin='md'),
                    BoxComponent(
                        layout='horizontal', spacing='sm', margin='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='幣別選單', text='幣別選單')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='日幣走勢', text='JPY 圖')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='美金匯率', text='USD'))
                        ]
                    ),
                    TextComponent(text="指令: 輸入幣別代碼 (如 USD, EUR)", size='xs', color='#999999', margin='xs', wrap=True),

                    SeparatorComponent(margin='md'),

                    # 2. 台股專區
                    TextComponent(text="📈 台股資訊", weight='bold', size='sm', color='#555555', margin='md'),
                    BoxComponent(
                        layout='horizontal', spacing='sm', margin='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='台積電', text='2330')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='台積電 K線', text='2330 日K')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='0050', text='0050'))
                        ]
                    ),
                    TextComponent(text="指令: {代號} 或 {代號} {K線/即時/交易量}", size='xs', color='#999999', margin='xs', wrap=True),

                    SeparatorComponent(margin='md'),

                    # 3. 美股專區
                    TextComponent(text="🇺🇸 美股報價", weight='bold', size='sm', color='#555555', margin='md'),
                    BoxComponent(
                        layout='horizontal', spacing='sm', margin='sm',
                        contents=[
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='蘋果', text='AAPL')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='輝達', text='NVDA')),
                            ButtonComponent(style='secondary', height='sm', action=MessageAction(label='VIX 指數', text='^VIX'))
                        ]
                    ),
                    TextComponent(text="指令: 輸入美股代碼 (如 TSLA, MSFT)", size='xs', color='#999999', margin='xs', wrap=True),
                    
                    SeparatorComponent(margin='md'),
                    
                    # Footer
                    ButtonComponent(style='link', height='sm', action=MessageAction(label='查詢 ID', text='ID'), margin='sm')
                ]
            )
        )
    )

def generate_currency_menu_flex():
    """產生熱門幣別選擇選單"""
    from config import VALID_CURRENCIES # Import locally if needed, or pass
    
    # 定義熱門 8 大幣別
    currencies = [
        {"code": "USD", "name": "美金"}, {"code": "JPY", "name": "日圓"},
        {"code": "EUR", "name": "歐元"}, {"code": "CNY", "name": "人民幣"},
        {"code": "KRW", "name": "韓元"}, {"code": "AUD", "name": "澳幣"},
        {"code": "GBP", "name": "英鎊"}, {"code": "THB", "name": "泰銖"}
    ]
    
    # Grid Layout: 2 columns x 4 rows
    rows = []
    current_row = []
    
    for i, curr in enumerate(currencies):
        btn = ButtonComponent(
            style='secondary', 
            height='sm',
            action=MessageAction(label=f"{curr['name']} ({curr['code']})", text=f"{curr['code']} 列表"), # 直接查列表
            flex=1
        )
        current_row.append(btn)
        
        # 每兩個換一行，或是最後一個
        if len(current_row) == 2 or i == len(currencies) - 1:
            rows.append(BoxComponent(layout='horizontal', spacing='sm', margin='sm', contents=current_row))
            current_row = []

    return FlexSendMessage(
        alt_text="請選擇幣別",
        contents=BubbleContainer(
            header=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text="🌏 選擇幣別", weight='bold', size='lg', color='#1DB446', align='center')
                ]
            ),
            body=BoxComponent(
                layout='vertical',
                contents=rows
            )
        )
    )

def generate_dashboard_flex_message(greeting_text, user_name, market_data):
    """
    產生市場快況儀表板 Flex Message
    greeting_text: 問候語 (e.g. "早安 🌞")
    user_name:使用者名稱 (e.g. "Joe")
    market_data: get_market_dashboard_data() 的回傳結果 list
    """
    
    # 建立 Dashboard Items (Vertical List)
    dashboard_rows = []
    
    for item in market_data:
        # Row for each market index
        row = BoxComponent(
            layout='baseline',
            spacing='sm',
            margin='md',
            action=MessageAction(label=item['name'], text=item['action_text']), # 點擊觸發查詢
            contents=[
               TextComponent(text=item['name'], size='sm', color='#555555', flex=4),
               TextComponent(text=item['price'], size='sm', weight='bold', align='end', flex=3),
               TextComponent(text=item['change_percent'], size='xs', color=item['color'], align='end', flex=3)
            ]
        )
        dashboard_rows.append(row)

    return FlexSendMessage(
        alt_text=f"{greeting_text}！市場快訊",
        contents=BubbleContainer(
            size='giga', # Make it wider
            body=BoxComponent(
                layout='vertical',
                contents=[
                    # Header Section with Greeting
                    TextComponent(text=f"{greeting_text}", weight='bold', size='xl', color='#1DB446'),
                    TextComponent(text=f"{user_name} 大帥哥！", weight='bold', size='lg', margin='xs'),
                    TextComponent(text="我是您的金融小幫手 🤖", size='xs', color='#aaaaaa', margin='xs'),
                    
                    SeparatorComponent(margin='md'),
                    
                    # Target Market Dashboard Header
                    TextComponent(text="📊 重點行情", size='sm', weight='bold', color='#999999', margin='md'),
                    
                    # Dashboard Rows (with fallback for empty data)
                    BoxComponent(
                        layout='vertical',
                        margin='sm',
                        contents=dashboard_rows if dashboard_rows else [
                            TextComponent(text="📡 資料載入中...", size='sm', color='#999999', align='center')
                        ]
                    ),
                    
                    SeparatorComponent(margin='lg'),
                    
                    # Footer Buttons
                    BoxComponent(
                        layout='horizontal',
                        margin='md',
                        spacing='sm',
                        contents=[
                            ButtonComponent(
                                style='secondary', height='sm', 
                                action=MessageAction(label='匯率選單', text='匯率選單')
                            ),
                            ButtonComponent(
                                style='secondary', height='sm', 
                                action=MessageAction(label='使用說明', text='使用說明')
                            )
                        ]
                    )
                ]
            )
        )
    )

def generate_us_stock_flex_message(data):
    """生成美股資訊 Flex Message（美股慣例：紅漲綠跌）"""
    # 美股顏色：紅漲綠跌
    color = "#eb4e3d" if data['change'] > 0 else "#27ba46" if data['change'] < 0 else "#333333"
    sign = "+" if data['change'] > 0 else ""
    
    # 格式化市值
    market_cap = data['market_cap']
    if market_cap > 1_000_000_000_000:
        market_cap_str = f"${market_cap/1_000_000_000_000:.2f}T"
    elif market_cap > 1_000_000_000:
        market_cap_str = f"${market_cap/1_000_000_000:.2f}B"
    elif market_cap > 1_000_000:
        market_cap_str = f"${market_cap/1_000_000:.2f}M"
    else:
        market_cap_str = f"${market_cap:,.0f}"
    
    return FlexSendMessage(
        alt_text=f"{data['symbol']} 美股",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"🇺🇸 {data['name']}", weight='bold', size='lg', wrap=True),
                    TextComponent(text=data['symbol'], size='sm', color='#999999', margin='xs'),
                    BoxComponent(
                        layout='baseline', margin='md',
                        contents=[
                            TextComponent(text=f"${data['price']:.2f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{data['change']:.2f} ({sign}{data['change_percent']:.2f}%)", 
                                        size='sm', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='lg', spacing='sm',
                        contents=[
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="最高", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"${data['high']:.2f}", align='end', size='sm', flex=2),
                                    TextComponent(text="最低", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"${data['low']:.2f}", align='end', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="成交量", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['volume']:,}", align='end', size='sm', flex=2),
                                    TextComponent(text="市值", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=market_cap_str, align='end', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="P/E", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=str(data['pe_ratio']) if data['pe_ratio'] != '-' else '-', 
                                                align='end', size='sm', flex=2),
                                    TextComponent(text="52週區間", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"${data['week_52_low']:.2f}-${data['week_52_high']:.2f}" 
                                                if data['week_52_high'] != '-' else '-', 
                                                align='end', size='xs', flex=2)
                                ]
                            )
                        ]
                    )
                ]
            )
        )
    )

def generate_stock_flex_message(data):
    color = "#eb4e3d" if data['change'] > 0 else "#27ba46" if data['change'] < 0 else "#333333"
    sign = "+" if data['change'] > 0 else ""
    
    return FlexSendMessage(
        alt_text=f"{data['symbol']} 股價",
        contents=BubbleContainer(
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=f"{data['name']} ({data['symbol']}) {data['type']}", weight='bold', size='xl'),
                    BoxComponent(
                        layout='baseline', margin='md',
                        contents=[
                            TextComponent(text=f"{data['price']:.2f}", weight='bold', size='3xl', color=color),
                            TextComponent(text=f"{sign}{data['change']:.2f} ({sign}{data['change_percent']:.2f}%)", size='sm', color=color, margin='md', flex=0)
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='lg', spacing='sm',
                        contents=[
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="漲停", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['limit_up']:.2f}", align='end', color='#eb4e3d', size='sm', flex=2),
                                    TextComponent(text="跌停", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['limit_down']:.2f}", align='end', color='#27ba46', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="最高", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['high']:.2f}", align='end', size='sm', flex=2),
                                    TextComponent(text="最低", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['low']:.2f}", align='end', size='sm', flex=2)
                                ]
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="成交(張)", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['volume']/1000:,.0f}", align='end', size='sm', flex=2),
                                    # Fugle 模式不顯示總量(股), 一般模式顯示
                                ] + ([
                                    TextComponent(text="總量(股)", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data['volume']:,.0f}", align='end', size='sm', flex=2)
                                ] if data.get('source') != 'fugle' else [TextComponent(text=" ", flex=3)])
                            ),
                            BoxComponent(
                                layout='baseline',
                                contents=[
                                    TextComponent(text="本益比", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data.get('twse_stats', {}).get('PE', '-')}", align='end', size='sm', flex=2),
                                    TextComponent(text="殖利率", color='#aaaaaa', size='sm', flex=1),
                                    TextComponent(text=f"{data.get('twse_stats', {}).get('Yield', '-')}%" if data.get('twse_stats', {}).get('Yield', '-') != '-' else '-', align='end', size='sm', flex=2)
                                ]
                            )
                        ]
                    ),
                    SeparatorComponent(margin='lg'),
                    BoxComponent(
                        layout='vertical', margin='md', spacing='sm',
                        contents=[
                            ButtonComponent(
                                style='primary', height='sm',
                                action=MessageAction(label='即時走勢圖', text=f"{data['symbol']} 即時")
                            ),
                            BoxComponent(
                                layout='horizontal', spacing='sm',
                                contents=[
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='日 K', text=f"{data['symbol']} 日K")),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='週 K', text=f"{data['symbol']} 週K")),
                                    ButtonComponent(style='secondary', height='sm', action=MessageAction(label='月 K', text=f"{data['symbol']} 月K"))
                                ]
                            ),
                            # Fugle 專屬功能: 52週股價
                            *(
                                [ButtonComponent(
                                     style='secondary', height='sm', margin='sm',
                                     action=MessageAction(label='近 52 週股價', text=f'{data["symbol"]} 52週')
                                )] if data.get('source') == 'fugle' else []
                            ),
                            ButtonComponent(
                                style='primary', color='#7000F0', height='sm', margin='sm',
                                action=MessageAction(label='AI 策略分析', text=f'{data["symbol"]} 分析')
                            ),
                            ButtonComponent(style='link', height='sm', action=MessageAction(label='近3日交易量', text=f"{data['symbol']} 交易量"))
                        ]
                    )
                ]
            )
        )
    )
