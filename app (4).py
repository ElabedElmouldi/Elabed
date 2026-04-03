import os
import requests
import ccxt
import pandas as pd
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات (تأكد من صحة التوكن والآيدي) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
TARGET_ID = "5067771509" 
EXCLUDED_COINS = ['BTC', 'ETH', 'USDT', 'USDC', 'BUSD', 'DAI', 'FDUSD']

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": TARGET_ID, "text": message, "parse_mode": "Markdown"}
    try:
        # زيادة وقت الانتظار (Timeout) لضمان الإرسال من السيرفرات البعيدة
        response = requests.post(url, json=payload, timeout=20)
        print(f"Telegram Log: {response.json()}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def scan_market():
    print("🔎 فحص السوق بدأ...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # فلترة وتصفية
        symbols = [s for s in tickers if s.endswith('/USDT') and 
                   s.split('/')[0] not in EXCLUDED_COINS and 
                   tickers[s]['quoteVolume'] > 1000000]
        
        # اختيار أفضل 40 عملة سيولة
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:40]
        
        for symbol in sorted_symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # حساب Bollinger Band Width (الضغط)
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
            
            last = df.iloc[-1]
            
            # شروط "أكثر مرونة" للاختبار
            if last['Width'] < 2.5 and 45 <= last['RSI'] <= 65:
                name = symbol.replace('/USDT', '')
                msg = f"✅ **إشارة جديدة:** #{name}\n💰 السعر: `{last['c']:.4f}`\n📊 ضغط: {last['Width']:.2f}% | RSI: {last['RSI']:.1f}"
                send_telegram_message(msg)
                
    except Exception as e:
        print(f"Scan Error: {e}")

# إعداد المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    # عند زيارة الرابط، سيقوم البوت بإرسال رسالة فورية للتأكد من أنه يعمل
    return "Bot is running! View logs for details."

if __name__ == "__main__":
    # تنبيه بسيط عند تشغيل السيرفر
    send_telegram_message("🚀 **البوت بدأ العمل على السيرفر!**")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
