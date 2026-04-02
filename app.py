import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام (ضع بياناتك هنا) ---
TOKEN = "ضـع_التوكـن_هـنا"
CHAT_ID = "ضـع_الـID_هـنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def calculate_indicators(df):
    # حساب RSI 14
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # حساب Bollinger Bands (20, 2)
    df['MA20'] = df['c'].rolling(window=20).mean()
    df['STD'] = df['c'].rolling(window=20).std()
    df['Lower_BB'] = df['MA20'] - (df['STD'] * 2)
    return df

def scan_binance():
    print("🔎 جاري فحص صفقات الـ 5%...")
    try:
        exchange = ccxt.binance()
        # فحص العملات الأساسية والأكثر تذبذبًا (يمكنك إضافة المزيد)
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT']
        
        for symbol in symbols:
            # جلب آخر 50 شمعة (فريم 15 دقيقة)
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df = calculate_indicators(df)
            
            last_row = df.iloc[-1]
            price = last_row['c']
            rsi = last_row['RSI']
            lower_bb = last_row['Lower_BB']

            # شروط الاستراتيجية: تشبع بيعي (RSI < 30) + لمس أسفل البولنجر
            # هذه المناطق تاريخياً تعطي ارتداد سريع بنسبة 3% إلى 6%
            if not np.isnan(rsi) and rsi < 32 and price <= lower_bb:
                target_5pct = price * 1.05
                stop_loss = price * 0.97
                
                msg = (
                    f"🎯 **فرصة سبوت (ارتداد متوقع)**\n\n"
                    f"العملة: #{symbol.split('/')[0]}\n"
                    f"💵 السعر الحالي: `{price:.4f}`\n"
                    f"✅ الهدف (+5%): `{target_5pct:.4f}`\n"
                    f"🛑 وقف الخسارة (-3%): `{stop_loss:.4f}`\n\n"
                    f"📊 مؤشر RSI: {rsi:.2f}"
                )
                send_telegram(msg)
                
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_binance, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Binance Scanner is Active..."

if __name__ == "__main__":
    # رسالة عند التشغيل
    send_telegram("🚀 تم تشغيل رادار الصفقات. سأقوم بإخطارك عند وجود فرص ارتداد بنسبة 5%.")
    scan_binance() # تشغيل فحص فوري
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
