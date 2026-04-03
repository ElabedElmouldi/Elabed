import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import time

app = Flask(__name__)

# ==========================================
# --- إعدادات التلجرام (تأكد من صحتها) ---
# ==========================================
TOKEN = "ضـع_تـوكن_البـوت_هـنا"
# ضع الأرقام هنا بدون أصفار في البداية (مثال: ["123456789"])
FRIENDS_IDS = ["ضـع_الـID_الخاص_بك_هنا"] 

STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USDS', 'EUR', 'GBP']

def send_to_all(message):
    """إرسال الرسائل مع طباعة النتيجة في سجلات رندر للتأكد"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                print(f"✅ Success: Message sent to {chat_id}")
            else:
                print(f"❌ Failed: {response.text}")
        except Exception as e:
            print(f"⚠️ Error: {str(e)}")

def send_welcome_message():
    """رسالة ترحيبية قوية عند الإقلاع"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg = (
        "🟢 **رادار الانفجارات السعرية متصل الآن!**\n"
        "━━━━━━━━━━━━━━━\n"
        f"📅 وقت التشغيل: `{now}`\n"
        "🤖 الحالة: يعمل بنظام الفلاتر المتقدمة (V4.3)\n"
        "📡 المراقبة: فريم 15 دقيقة / تأكيد 4 ساعات\n"
        "━━━━━━━━━━━━━━━\n"
        "✨ سأبدأ الآن بفحص السوق وإرسال أولى الصفقات..."
    )
    send_to_all(msg)

def send_heartbeat():
    now = datetime.now().strftime('%H:%M')
    msg = f"🔔 **تحديث دوري:** البوت يعمل بكفاءة. (توقيت تونس: {now})"
    send_to_all(msg)

# --- دوال التحليل الفني ---
def get_data(exchange, symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    except: return pd.DataFrame()

def calculate_indicators(df):
    if df.empty: return df
    df['MA20'] = df['c'].rolling(20).mean()
    df['STD'] = df['c'].rolling(20).std()
    df['Lower'] = df['MA20'] - (df['STD'] * 2)
    df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    mfv = ((df['c'] - df['l']) - (df['h'] - df['c'])) / (df['h'] - df['l'] + 1e-9) * df['v']
    df['CMF'] = mfv.rolling(20).sum() / (df['v'].rolling(20).sum() + 1e-9)
    df['TR'] = np.maximum((df['h'] - df['l']), np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['ATR'] = df['TR'].rolling(14).mean()
    return df

def scan_market():
    print("🔎 Scanning Market...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            vol_24h = tickers[symbol]['quoteVolume']
            if 10_000_000 <= vol_24h <= 300_000_000:
                df_4h = get_data(exchange, symbol, '4h', 50)
                if df_4h.empty or df_4h['c'].iloc[-1] < df_4h['c'].ewm(span=50).mean().iloc[-1]:
                    continue
                
                df_15m = get_data(exchange, symbol, '15m', 100)
                df_15m = calculate_indicators(df_15m)
                if df_15m.empty: continue
                last = df_15m.iloc[-1]

                if last['Width'] < 1.2 and 55 <= last['RSI'] <= 65 and last['CMF'] > 0:
                    entry = last['c']
                    target = entry + (last['ATR'] * 3)
                    stop = last['Lower']
                    profit_pct = ((target - entry) / entry) * 100
                    loss_pct = ((entry - stop) / entry) * 100
                    
                    if profit_pct >= 5.0:
                        msg = (
                            f"🌋 **إشارة انفجار (+{profit_pct:.1f}%)**\n"
                            f"العملة: #{symbol.replace('/USDT', '')}\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"📥 **دخول:** `{entry:.4f}`\n"
                            f"🛑 **وقف:** `{stop:.4f}` ({loss_pct:.1f}-%)\n"
                            f"🎯 **هدف:** `{target:.4f}`\n"
                            f"📊 RSI: `{last['RSI']:.1f}` | CMF: `{last['CMF']:.2f}`"
                        )
                        send_to_all(msg)
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.add_job(send_heartbeat, 'interval', hours=2)
scheduler.start()

@app.route('/')
def home():
    return "Bot is Active!"

if __name__ == "__main__":
    # تشغيل الرسالة الترحيبية مع تأخير بسيط لضمان اتصال الشبكة
    time.sleep(5) 
    send_welcome_message()
    
    # تشغيل أول فحص
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
