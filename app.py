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
TARGET_ID = "5067771509" 

# قائمة العملات المستبعدة
EXCLUDED_COINS = ['BTC', 'ETH', 'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USTC', 'EUR', 'GBP']

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": TARGET_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def scan_for_explosion():
    print("🔄 جاري فحص العملات البديلة...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        symbols = []
        for s in tickers:
            if s.endswith('/USDT'):
                coin_name = s.split('/')[0]
                # تصفية العملات المستقرة و BTC/ETH وحجم التداول
                if coin_name not in EXCLUDED_COINS and tickers[s]['quoteVolume'] > 1000000:
                    symbols.append(s)

        # ترتيب حسب السيولة واختيار أعلى 30
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
            
            # الشروط: ضغط أقل من 2% و RSI بين 50-60
            if last['Width'] < 2.0 and 50 <= last['RSI'] <= 60:
                entry = last['c']
                name = symbol.replace('/USDT', '')
                msg = (
                    f"⚡️ **إشارة عملة بديلة (Altcoin)**\n"
                    f"العملة: #{name}\n"
                    f"السعر: `{entry:.4f}`\n"
                    f"📊 RSI: {last['RSI']:.2f} | الضغط: {last['Width']:.2f}%"
                )
                send_telegram_message(msg)
                
    except Exception as e:
        print(f"Error: {e}")

# --- تشغيل المجدول بشكل صحيح ---
scheduler = BackgroundScheduler(daemon=True)
# إضافة الوظيفة لتعمل كل 15 دقيقة
scheduler.add_job(func=scan_for_explosion, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Bot is Active and Scanning Altcoins!"

if __name__ == "__main__":
    # إرسال رسالة تنبيه عند بدء التشغيل للتأكد من أنه يعمل
    send_telegram_message("✅ تم إعادة تشغيل البوت بنجاح وهو الآن يراقب العملات البديلة فقط.")
    
    # الحصول على المنفذ (Port) الخاص بالاستضافة
    port = int(os.environ.get("PORT", 10000))
    # تشغيل Flask
    app.run(host='0.0.0.0', port=port)
