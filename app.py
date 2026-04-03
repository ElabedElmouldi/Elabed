import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from capitals_scheduler import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
TARGET_ID = "5067771509" 

# قائمة العملات المستبعدة (العملات المستقرة والعملات القيادية)
EXCLUDED_COINS = [
    'BTC', 'ETH', 'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USTC', 'EUR', 'GBP'
]

def send_telegram_message(message):
    """إرسال الرسالة للمعرف المحدد فقط"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Connection Error: {e}")

def scan_for_explosion():
    print("🚀 جاري فحص العملات البديلة (Altcoins) فقط...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # تصفية العملات: 
        # 1. تنتهي بـ USDT
        # 2. ليست في القائمة السوداء (EXCLUDED_COINS)
        # 3. حجم تداول محترم
        symbols = []
        for s in tickers:
            if s.endswith('/USDT'):
                coin_name = s.split('/')[0]
                if coin_name not in EXCLUDED_COINS and tickers[s]['quoteVolume'] > 1000000:
                    symbols.append(s)

        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]
        
        for symbol in sorted_symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # حساب انضغاط البولنجر
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Upper'] = df['MA20'] + (df['STD'] * 2)
            df['Lower'] = df['MA20'] - (df['STD'] * 2)
            df['Width'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100
            
            last = df.iloc[-1]
            
            # شروط الاستراتيجية
            if last['Width'] < 2.0 and 50 <= last['RSI'] <= 60:
                entry = last['c']
                target = entry * 1.05
                stop = entry * 0.97
                
                name = symbol.replace('/USDT', '')
                msg = (
                    f"⚡️ **انفجار سعري مرتقب (Altcoin)**\n"
                    f"العملة: #{name}\n\n"
                    f"📥 **الدخول:** `{entry:.4f}`\n"
                    f"🎯 **الهدف:** `{target:.4f}`\n"
                    f"🛑 **الوقف:** `{stop:.4f}`\n\n"
                    f"📊 RSI: {last['RSI']:.2f} | ضغط: {last['Width']:.2f}%"
                )
                send_telegram_message(msg)
                
    except Exception as e:
        print(f"Scan Error: {e}")

# المجدول الزمني
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>البوت يفحص العملات البديلة بنجاح!</h1>"

if __name__ == "__main__":
    scan_for_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
