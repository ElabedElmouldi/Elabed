import ccxt
import pandas as pd
import time
from datetime import datetime
from flask import Flask
from threading import Thread
import os

# --- 1. إعداد خادم الويب (Flask) ---
app = Flask('')

@app.route('/')
def home():
    return f"البوت يعمل بنجاح! الوقت الحالي: {datetime.now().strftime('%H:%M:%S')}"

def run_web_server():
    # Render يستخدم المنفذ 10000 افتراضياً
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. إعدادات البوت والبيانات ---
exchange = ccxt.binance({'enableRateLimit': True})

VIRTUAL_BALANCE = 100.0
PERCENT_PER_TRADE = 0.20
MAX_TRADES = 5
TARGET_PROFIT = 1.04
STOP_LOSS = 0.98

active_trades = []

def get_top_gainers():
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        for s, d in tickers.items():
            if '/USDT' in s and d['quoteVolume'] > 10000000:
                gainers.append({'symbol': s, 'percentage': d['percentage']})
        gainers.sort(key=lambda x: x['percentage'], reverse=True)
        return [item['symbol'] for item in gainers[:100]]
    except: return []

# --- 3. المنطق الأساسي مع الرسالة الترحيبية ---
def run_trading_logic():
    global VIRTUAL_BALANCE
    
    # رسالة ترحيبية واضحة تظهر في سجل Render (Logs)
    print("\n" + "*"*50)
    print(f"🚀 [نظام التداول الذكي] بدأ العمل الآن!")
    print(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"💰 الرصيد الافتراضي المخصص: {VIRTUAL_BALANCE}$")
    print(f"🎯 الهدف: +4% لكل صفقة | الوقف: -2%")
    print(f"🔍 البحث في أفضل 100 عملة صاعدة (Top Gainers)")
    print("*"*50 + "\n")

    while True:
        try:
            symbols = get_top_gainers()
            
            if len(active_trades) < MAX_TRADES:
                entry_amount = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    # (هنا نضع منطق RSI و Bollinger الذي صممناه سابقاً)
                    # ... كود التحليل ...
                    
                    # مثال عند الدخول:
                    # print(f"🔔 [إشعار] تم دخول صفقة في {symbol} بمبلغ {entry_amount:.2f}$")
            
            time.sleep(30)
        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            time.sleep(20)

# --- 4. نقطة الانطلاق الصحيحة ---
if __name__ == "__main__":
    # تشغيل السيرفر في خيط منفصل (Background Thread)
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True # لضمان إغلاقه عند إغلاق البرنامج الرئيسي
    server_thread.start()
    
    # تشغيل البوت في الخيط الرئيسي (Main Thread)
    # هذا يضمن أن الرسالة الترحيبية تظهر فوراً في الـ Console
    run_trading_logic()
