import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات الشخصية للمحادثة المباشرة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
# ضـع رقـم الـ ID الخـاص بـك (الذي حصلت عليه من @userinfobot)
# لا يجب أن يبدأ بـ -100 هنا، بل يكون رقماً عادياً (مثال: 58493021)
MY_CHAT_ID = "5067771509" 

def send_telegram(message):
    """إرسال التنبيهات إلى محادثتك الشخصية مع البوت"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": MY_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"📡 Status: {response.status_code} | Log: {response.json()}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def calculate_rsi(df, period=14):
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def scan_market():
    print("🔎 فحص أعلى 20 عملة (Volume) وإرسال النتائج لك...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        usdt_tickers = [s for s in tickers if s.endswith('/USDT')]
        
        # فرز العملات حسب الفوليم واختيار أعلى 20
        sorted_tickers = sorted(usdt_tickers, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        top_20 = sorted_tickers[:20]
        
        matches = []
        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['RSI'] = calculate_rsi(df)
            last_rsi = df['RSI'].iloc[-1]
            
            # الشرط المطلوب: RSI بين 50 و 60
            if 50 <= last_rsi <= 60:
                clean_name = symbol.replace('/USDT', '')
                matches.append(f"💰 *{clean_name}* | RSI: `{last_rsi:.2f}`")

        if matches:
            report = "📊 **تقرير السيولة (RSI 50-60):**\n\n"
            report += "\n".join(matches)
            send_telegram(report)
            
    except Exception as e:
        print(f"❌ Scan Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>البوت يعمل ويرسل لك مباشرة!</h1>"

if __name__ == "__main__":
    # رسالة ترحيب فورية للتأكد من الاتصال
    send_telegram("🚀 **تم التحويل بنجاح!**\nسأرسل لك الآن تقارير العملات القوية هنا مباشرة.")
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
