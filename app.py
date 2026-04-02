import os
import time
import requests # سنستخدم requests لضمان وصول الرسائل ببساطة وقوة
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import ccxt
import pandas as pd
import numpy as np

app = Flask(__name__)

# --- الإعدادات ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ضعه_هنا")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضعه_هنا")

def send_telegram_instant(message):
    """إرسال رسالة فورية باستخدام API التلجرام المباشر (أكثر استقراراً للسيرفرات)"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        print(f"📡 Telegram Response: {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"❌ Error sending to Telegram: {e}")
        return None

# --- الحسابات الرياضية ---
def calculate_indicators(df):
    # RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands
    sma = df['c'].rolling(window=20).mean()
    std = df['c'].rolling(window=20).std()
    df['Lower_BB'] = sma - (std * 2)
    return df

def scan_market():
    print("🔍 جاري فحص السوق...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP' not in s and 'DOWN' not in s]
        
        # تحليل أعلى 10 عملات سيولة فقط لتوفير الجهد على السيرفر المجاني
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_10 = df_vol.sort_values(by='v', ascending=False).head(10)['s'].tolist()
        
        for symbol in top_10:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df = calculate_indicators(df)
            
            last = df.iloc[-1]
            if not np.isnan(last['RSI']) and last['RSI'] < 35 and last['c'] <= last['Lower_BB']:
                entry = last['c']
                msg = (
                    f"🎯 **فرصة سبوت مؤكدة!**\n"
                    f"العملة: #{symbol.split('/')[0]}\n"
                    f"💵 الدخول: `{entry:.4f}`\n"
                    f"🎯 الهدف (+6%): `{entry * 1.06:.4f}`\n"
                    f"🛑 الوقف (-3%): `{entry * 0.97:.4f}`"
                )
                send_telegram_instant(msg)
    except Exception as e:
        print(f"❌ Scan Error: {e}")

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=scan_market, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>Status: Active</h1><p>الرادار يعمل ويرسل الإشعارات الآن.</p>"

if __name__ == "__main__":
    # رسالة ترحيب فورية عند التشغيل (هنا سنعرف إذا كان الربط شغال)
    send_telegram_instant("🚀 **تم تشغيل الرادار بنجاح!**\nأنا الآن أراقب السوق كل 15 دقيقة.")
    
    # تشغيل فحص أولي
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
