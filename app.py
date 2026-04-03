import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    """إرسال الرسائل لجميع المشتركين"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")

def get_4h_trend(exchange, symbol):
    """التأكد من أن الاتجاه العام صاعد على فريم 4 ساعات"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        ema_100 = df['c'].ewm(span=100, adjust=False).mean().iloc[-1]
        return df['c'].iloc[-1] > ema_100
    except: return False

def scan_market():
    """البحث عن انفجارات سعرية مدعومة بسيولة واتجاه صاعد"""
    print("🔎 جاري فحص الفرص...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # اختيار العملات النشطة (سيولة > 1.5 مليون)
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 1500000]
        top_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]

        for symbol in top_symbols:
            if not get_4h_trend(exchange, symbol): continue

            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

            # حساب البولنجر والسيولة والـ RSI
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
            df['Vol_MA'] = df['v'].rolling(20).mean()
            
            # حساب RSI
            delta = df['c'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))

            last = df.iloc[-1]
            if last['Width'] < 2.0 and 52 <= rsi.iloc[-1] <= 62 and last['v'] > (last['Vol_MA'] * 1.5):
                price = last['c']
                msg = (f"🧨 **إشارة انفجار مؤكدة**\n"
                       f"العملة: #{symbol.replace('/USDT', '')}\n"
                       f"الاتجاه (4H): ✅ صاعد\n\n"
                       f"📥 دخول: `{price:.4f}`\n"
                       f"🎯 هدف (6%): `{price*1.06:.4f}`\n"
                       f"🛑 وقف (3%): `{price*0.97:.4f}`")
                send_telegram(msg)
    except Exception as e: print(f"Scan Error: {e}")

def heartbeat():
    send_telegram("🟢 **نبضة القلب:** البوت يعمل ومستمر في المراقبة.")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.add_job(heartbeat, 'interval', minutes=60)
scheduler.start()

@app.route('/')
def home(): return "Trading Bot is Active!"

if __name__ == "__main__":
    send_telegram("🚀 **تم تشغيل البوت عبر Docker!**")
    scan_market()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
