import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام ---
TOKEN = "ضـع_التوكـن_هـنا"
MY_CHAT_ID = "ضـع_رقم_الـID_الخاص_بك_هنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": MY_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def scan_for_explosion():
    print("🚀 جاري البحث عن عملات الانفجار السعري...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        # اختيار أعلى 30 عملة سيولة مقابل USDT
        symbols = [s for s in tickers if s.endswith('/USDT')]
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]
        
        potential_booms = []

        for symbol in sorted_symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # حساب انضغاط البولنجر (Squeeze)
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Upper'] = df['MA20'] + (df['STD'] * 2)
            df['Lower'] = df['MA20'] - (df['STD'] * 2)
            
            # حساب نسبة الانضغاط (Width)
            df['Width'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100
            
            last = df.iloc[-1]
            
            # --- شروط الانفجار السعري ---
            # 1. انضغاط شديد (Width < 2%)
            # 2. RSI في منطقة قوة (50-65)
            if last['Width'] < 2.0 and 50 <= last['RSI'] <= 65:
                name = symbol.replace('/USDT', '')
                potential_booms.append(
                    f"🔥 *{name}* \n"
                    f"📉 انضغاط: `{last['Width']:.2f}%` (انفجار قريب)\n"
                    f"📊 RSI: `{last['RSI']:.2f}`\n"
                    f"💵 السعر: `{last['c']}`"
                )

        if potential_booms:
            msg = "⚠️ **رادار الانفجار السعري القادم!**\n"
            msg += "عملات في مرحلة ضغط شديد (Squeeze):\n\n"
            msg += "\n---\n".join(potential_booms)
            send_telegram(msg)
            
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Explosion Radar is Active..."

if __name__ == "__main__":
    send_telegram("🚀 **تم تفعيل رادار الانفجارات!**\nسأبحث عن العملات المنضغطة حالياً.")
    scan_for_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
