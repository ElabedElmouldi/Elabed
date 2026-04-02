import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات (تأكد من وضع قيمك هنا) ---
TOKEN = "ضـع_التوكـن_هـنا"
CHAT_ID = "ضـع_الـID_هـنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def scan_market():
    print("🔎 فحص السوق جارٍ...")
    try:
        exchange = ccxt.binance()
        # فحص أهم 5 عملات لتقليل الضغط على السيرفر المجاني
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'AVAX/USDT']
        
        for symbol in symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI مبسط
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # حساب البولنجر
            df['MA20'] = df['c'].rolling(window=20).mean()
            df['STD'] = df['c'].rolling(window=20).std()
            df['Lower_BB'] = df['MA20'] - (df['STD'] * 2)
            
            last = df.iloc[-1]
            if not np.isnan(last['RSI']) and last['RSI'] < 32 and last['c'] <= last['Lower_BB']:
                price = last['c']
                msg = (
                    f"🎯 **فرصة سبوت محتملة!**\n"
                    f"العملة: {symbol}\n"
                    f"💵 السعر: `{price:.4f}`\n"
                    f"✅ الهدف (+5%): `{price * 1.05:.4f}`\n"
                    f"🛑 الوقف (-3%): `{price * 0.97:.4f}`"
                )
                send_telegram(msg)
    except Exception as e:
        print(f"Scan Error: {e}")

# إعداد المجدول ليعمل كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def health_check():
    return "Bot is Alive and Scanning!"

if __name__ == "__main__":
    # رسالة ترحيب فورية عند التشغيل
    send_telegram("🚀 السلام عليكم، البوت يعمل بنجاح وبدأ فحص السوق.")
    # تشغيل فحص أولي فوراً
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
