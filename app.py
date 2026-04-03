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
# --- إعدادات التلجرام (تأكد من الـ ID والتوكن) ---
# ==========================================
TOKEN = "ضـع_تـوكن_البـوت_هـنا"
FRIENDS_IDS = ["ضـع_الـID_الخاص_بك_هنا"] 

STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USDS', 'EUR', 'GBP']

def send_to_telegram(message):
    """إرسال الرسائل لجميع المشتركين"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error sending message: {e}")

def send_heartbeat():
    """رسالة دورية لتأكيد عمل البوت (كل ساعتين)"""
    now = datetime.now().strftime('%H:%M')
    msg = (
        f"🤖 **تحديث دوري للنظام**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏱ الوقت الحالي: `{now}` (توقيت تونس)\n"
        f"📡 الحالة: أراقب السوق بحثاً عن انفجارات سعرية..\n"
        f"⚙️ الاستراتيجية: Bollinger Squeeze + Volume Spike"
    )
    send_to_telegram(msg)

def calculate_explosion_logic(symbol, df_15m, df_4h):
    """خوارزمية اكتشاف الانفجار السعري"""
    # 1. حساب البولنجر وفلتر الضغط (Squeeze)
    df_15m['MA20'] = df_15m['c'].rolling(20).mean()
    df_15m['STD'] = df_15m['c'].rolling(20).std()
    df_15m['Upper'] = df_15m['MA20'] + (df_15m['STD'] * 2)
    df_15m['Lower'] = df_15m['MA20'] - (df_15m['STD'] * 2)
    df_15m['Width'] = (df_15m['Upper'] - df_15m['Lower']) / df_15m['MA20'] * 100

    # 2. فلتر السيولة (Volume Spike)
    avg_vol = df_15m['v'].rolling(20).mean().iloc[-1]
    current_vol = df_15m['v'].iloc[-1]

    # 3. فلتر الاتجاه (4 ساعات)
    ema_50_4h = df_4h['c'].ewm(span=50).mean().iloc[-1]
    price_4h = df_4h['c'].iloc[-1]

    last = df_15m.iloc[-1]
    
    # الشروط: ضغط < 1.2% + سيولة > 1.8x المتوسط + اتجاه صاعد 4H
    if last['Width'] < 1.2 and current_vol > (avg_vol * 1.8) and price_4h > ema_50_4h:
        entry = last['c']
        # حساب وقف الخسارة والهدف ديناميكياً
        atr = (df_15m['h'] - df_15m['l']).rolling(14).mean().iloc[-1]
        target = entry + (atr * 3)
        stop = last['Lower']
        
        profit_pct = ((target - entry) / entry) * 100
        loss_pct = ((entry - stop) / entry) * 100

        if profit_pct >= 5.0:
            msg = (
                f"🌋 **إشارة: انفجار سعري مكتشف!**\n"
                f"العملة: #{symbol.replace('/USDT', '')}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📥 **دخول:** `{entry:.4f}`\n"
                f"🎯 **هدف (+{profit_pct:.1f}%):** `{target:.4f}`\n"
                f"🛑 **وقف (-{loss_pct:.1f}%):** `{stop:.4f}`\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📊 **بيانات الضغط:** `{last['Width']:.2f}%` ⚠️\n"
                f"📈 **قوة السيولة:** `x{current_vol/avg_vol:.1f}` 🚀"
            )
            send_to_telegram(msg)

def run_scanner():
    print("🔎 Scanning market for explosions...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        # تصفية عملات النطاق الذهبي (10M - 300M volume)
        symbols = [s for s in tickers if s.endswith('/USDT') and 
                   10_000_000 <= tickers[s]['quoteVolume'] <= 300_000_000 and 
                   s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)
            df_15m = pd.DataFrame(bars_15m, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            calculate_explosion_logic(symbol, df_15m, df_4h)
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
# فحص السوق كل 15 دقيقة
scheduler.add_job(run_scanner, 'interval', minutes=15)
# إرسال رسالة "أنا أعمل" كل ساعتين
scheduler.add_job(send_heartbeat, 'interval', hours=2)
scheduler.start()

@app.route('/')
def home():
    return "<h1>Explosion Radar V5.1 is Active!</h1>"

if __name__ == "__main__":
    # رسالة ترحيبية فور التشغيل
    time.sleep(2)
    send_to_telegram("✅ **تم تفعيل رادار الانفجار السعري V5.1**\nأنا الآن أراقب السوق 24/7 وسأرسل لك تحديثاً كل ساعتين.")
    
    run_scanner()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
