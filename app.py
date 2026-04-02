import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام (تأكد من وضع بياناتك هنا) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
CHAT_ID = "5067771509"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def calculate_rsi(df, period=14):
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def scan_market():
    print("🔎 جاري فحص أعلى 20 عملة فوليم (RSI 50-60)...")
    try:
        exchange = ccxt.binance()
        # 1. جلب بيانات جميع العملات مقابل USDT
        tickers = exchange.fetch_tickers()
        usdt_tickers = [symbol for symbol in tickers if symbol.endswith('/USDT')]
        
        # 2. فرز العملات حسب الفوليم (Quote Volume) واختيار أعلى 20
        sorted_tickers = sorted(usdt_tickers, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        top_20_symbols = sorted_tickers[:20]
        
        found_opportunities = []

        for symbol in top_20_symbols:
            # جلب شموع 15 دقيقة
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI
            df['RSI'] = calculate_rsi(df)
            last_rsi = df['RSI'].iloc[-1]
            
            # 3. الشرط المطلوب: RSI بين 50 و 60
            if 50 <= last_rsi <= 60:
                found_opportunities.append(f"✅ *{symbol.split('/')[0]}* (RSI: {last_rsi:.2f})")

        # 4. إرسال النتائج في رسالة واحدة
        if found_opportunities:
            message = "📊 **عملات الـ Volume العالي (RSI 50-60):**\n\n" + "\n".join(found_opportunities)
            send_telegram(message)
        else:
            # اختياري: إرسال رسالة في حال لم يتم العثور على أي عملة تطابق الشرط
            print("لم يتم العثور على عملات تطابق شروط RSI الحالية.")

    except Exception as e:
        print(f"Scan Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def health():
    return "Scanner is Running (Top 20 Volume - RSI 50-60)"

if __name__ == "__main__":
    # رسالة ترحيب
    send_telegram("🚀 تم تفعيل رادار الـ Volume العالي (RSI 50-60).")
    # تشغيل فحص فوري
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
