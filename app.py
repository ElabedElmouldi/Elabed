import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

# تم الإبقاء على الأيدي الأول فقط كما طلبت
TARGET_ID = "5067771509" 



def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": TARGET_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=15)
        # هذا السطر سيطبع لك الرد القادم من تلجرام في الـ Logs
        print(f"Telegram Response: {response.json()}") 
        if not response.json().get("ok"):
            print(f"❌ فشل الإرسال: {response.json().get('description')}")
    except Exception as e:
        print(f"📡 خطأ في الاتصال: {e}")


def scan_for_explosion():
    print("🚀 جاري فحص السوق وإرسال الصفقات...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # تصفية العملات ذات السيولة الجيدة (أكثر من مليون دولار حجم تداول)
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 1000000]
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]
        
        for symbol in sorted_symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
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
            
            # الشروط: انضغاط أقل من 2% و RSI بين 50 و 60
            if last['Width'] < 2.0 and 50 <= last['RSI'] <= 60:
                entry = last['c']
                target = entry * 1.05 # هدف 5%
                stop = entry * 0.97  # وقف 3%
                
                name = symbol.replace('/USDT', '')
                msg = (
                    f"⚡️ **توصية انفجار سعري (خاصة)**\n"
                    f"العملة: #{name}\n\n"
                    f"📥 **سعر الدخول:** `{entry:.4f}`\n"
                    f"🎯 **الهدف:** `{target:.4f}`\n"
                    f"🛑 **الوقف:** `{stop:.4f}`\n\n"
                    f"📊 RSI: {last['RSI']:.2f} | الضغط: {last['Width']:.2f}%"
                )
                send_telegram_message(msg)
                
    except Exception as e:
        print(f"Scan Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return f"<h1>البوت يعمل ويرسل التقارير إلى المعرف: {TARGET_ID}</h1>"

if __name__ == "__main__":
    send_telegram_message("🚀 **تم تشغيل البوت بنجاح!**\nسيتم إرسال التنبيهات إليك هنا مباشرة.")
    scan_for_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
