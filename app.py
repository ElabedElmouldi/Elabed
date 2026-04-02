import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام للقناة الخاصة ---
TOKEN = "> Dream Agency:8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68
"
# الـ ID الخاص بالقناة يجب أن يبدأ بـ -100
CHANNEL_ID = "1003692815602" 

def send_telegram(message):
    """إرسال التنبيهات إلى القناة الخاصة"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        # طباعة الرد في السجلات للتأكد من نجاح الإرسال
        print(f"Telegram Log: {response.json()}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def calculate_rsi(df, period=14):
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def scan_market():
    print("🔎 فحص أعلى 20 عملة (Volume) وإرسال النتائج للقناة...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        usdt_tickers = [s for s in tickers if s.endswith('/USDT')]
        
        # فرز حسب السيولة (Volume) واختيار أعلى 20
        sorted_tickers = sorted(usdt_tickers, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        top_20 = sorted_tickers[:20]
        
        matches = []
        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['RSI'] = calculate_rsi(df)
            last_rsi = df['RSI'].iloc[-1]
            
            # شرط RSI بين 50 و 60
            if 50 <= last_rsi <= 60:
                matches.append(f"🔸 *{symbol.replace('/USDT', '')}* | RSI: `{last_rsi:.2f}`")

        if matches:
            report = "📢 **تنبيه الرادار (قناة خاصة)**\n"
            report += "العملات الأكثر سيولة بـ RSI (50-60):\n\n"
            report += "\n".join(matches)
            send_telegram(report)
            
    except Exception as e:
        print(f"Scan Error: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def health():
    return "Bot is Broadcasting to Private Channel..."

if __name__ == "__main__":
    # رسالة عند التشغيل للتأكد من أن القناة استقبلت البوت
    send_telegram("🚀 **تم تفعيل البوت بنجاح!**\nبدأ الآن إرسال تقارير السيولة إلى هذه القناة.")
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
