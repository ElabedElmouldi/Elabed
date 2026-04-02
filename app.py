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
MY_CHAT_ID = "ضـع_رقم_الـID_الخاص_بك_هنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": MY_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def scan_for_explosion():
    print("🚀 جاري البحث عن صفقات الانفجار (الهدف 6%)...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT')]
        # فحص أعلى 30 عملة سيولة
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
            
            # --- شروط الصفقة ---
            # انضغاط أقل من 2% و RSI في منطقة قوة (50-60)
            if last['Width'] < 2.0 and 50 <= last['RSI'] <= 60:
                entry_price = last['c']
                target_price = entry_price * 1.06  # هدف 6%
                stop_loss = entry_price * 0.97    # وقف 3%
                
                name = symbol.replace('/USDT', '')
                msg = (
                    f"⚡️ **إشارة انفجار سعري قادمة**\n"
                    f"العملة: #{name}\n\n"
                    f"📥 **سعر الدخول:** `{entry_price:.4f}`\n"
                    f"🎯 **الهدف (6%+):** `{target_price:.4f}`\n"
                    f"🛑 **وقف الخسارة (3%-):** `{stop_loss:.4f}`\n\n"
                    f"📊 RSI: {last['RSI']:.2f} | الضغط: {last['Width']:.2f}%"
                )
                send_telegram(msg)
                
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Bot is Active - Strategy: 6% Target / 3% Stop"

if __name__ == "__main__":
    send_telegram("🚀 **تم تشغيل رادار الصفقات المطور!**\nسأرسل لك نقاط الدخول والخروج بدقة.")
    scan_for_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
