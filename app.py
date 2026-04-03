import os
import requests
import ccxt
import pandas as pd
import numpy as np
import time
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import logging

# 1. إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية الأصلية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
APP_URL = os.getenv("APP_URL") 

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def get_btc_status(exchange):
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -2.0 # يسمح بالعمل إذا كان هبوط البيتكوين أخف من 2%
    except: return True

def scan_market():
    logger.info("🔎 جاري فحص السوق بحثاً عن انفجارات سعرية...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): return

        tickers = exchange.fetch_tickers()
        
        # --- تعديل قائمة العملات ---
        # سنقوم بفحص كل عملات USDT التي يتجاوز حجم تداولها 1,000,000 دولار
        symbols = [
            s for s in tickers 
            if s.endswith('/USDT') 
            and (tickers[s].get('quoteVolume') or 0) > 1000000 
            and 'UP' not in s and 'DOWN' not in s # استبعاد عملات الرافعة المالية
        ]
        
        # ترتيب العملات حسب السيولة (الأعلى أولاً) واختيار أفضل 150 عملة
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        target_symbols = sorted_symbols[:150] 

        for symbol in target_symbols:
            try:
                # فريم 15 دقيقة للتحليل
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # حساب القمة السابقة (أعلى سعر في آخر 15 شمعة)
                recent_high = df['h'].iloc[-16:-1].max()
                current_price = df['c'].iloc[-1]
                
                # حساب المؤشرات (بإعدادات أكثر مرونة)
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100 # نطاق البولنجر
                df['Vol_MA'] = df['v'].rolling(20).mean() # متوسط السيولة
                
                # حساب RSI
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # --- الشروط المعدلة لاصطياد الفرص ---
                is_breaking = current_price >= recent_high # اختراق القمة
                has_volume_spike = last['v'] > (last['Vol_MA'] * 1.8) # سيولة 1.8 ضعف (بدلاً من 3)
                is_ready = last['Width'] < 4.0 # انضغاط سعري معقول (بدلاً من 2)
                has_momentum = 50 <= last['RSI'] <= 72 # زخم ممتاز

                if is_breaking and has_volume_spike and is_ready and has_momentum:
                    # تأكيد الاتجاه الصاعد على EMA 20 (فريم ساعة)
                    bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=30)
                    df_1h = pd.DataFrame(bars_1h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_20 = df_1h['c'].ewm(span=20, adjust=False).mean().iloc[-1]
                    
                    if current_price > ema_20:
                        msg = (f"🚀 **إشارة انفجار سعري (Spot)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"الوضع: اختراق + سيولة قوية\n\n"
                               f"💰 السعر الحالي: `{current_price:.4f}`\n"
                               f"🎯 هدف (5%): `{current_price*1.05:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
                        logger.info(f"Signal sent for {symbol}")
                        time.sleep(1) # تأخير بسيط لتجنب حظر التلغرام
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

# --- وظيفة Keep Alive ---
def keep_alive():
    while True:
        if APP_URL:
            try:
                requests.get(APP_URL, timeout=10)
                logger.info("📡 Self-Ping successful.")
            except: pass
        time.sleep(600)

# المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def home(): 
    return "<h1>Fast Lane Bot v5.3 - Scanning 150 Symbols</h1>"

if __name__ == "__main__":
    send_telegram("✅ تم تحديث قائمة العملات (أفضل 150 عملة سيولة).\nالبوت يبحث الآن عن اختراقات قريبة.")
    scan_market()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
