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

# 1. إعداد السجلات (Logs) لمراقبة الأداء
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الآمنة (Environment Variables) ---
TOKEN = os.getenv("8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
FRIENDS_IDS_RAW = os.getenv("FRIENDS_IDS", "")
FRIENDS_IDS = [fid.strip() for fid in FRIENDS_IDS_RAW.split(",") if fid.strip()]
APP_URL = os.getenv("APP_URL") # ضع رابط تطبيقك هنا (مثال: https://fast-lane-bot.onrender.com)

def send_telegram(message):
    if not TOKEN or not FRIENDS_IDS: return
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def get_btc_status(exchange):
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -1.5 
    except: return True

def scan_market():
    logger.info("🏇 دورة فحص جديدة بدأت...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): return

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 1000000]
        
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        fast_lane_symbols = sorted_symbols[50:150] 

        for symbol in fast_lane_symbols:
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                recent_high = df['h'].iloc[-21:-1].max()
                current_price = df['c'].iloc[-1]
                
                # المؤشرات الفنية
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(30).mean()
                
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # شروط الانفجار
                if last['Width'] < 2.0 and current_price > recent_high and last['v'] > (last['Vol_MA'] * 3.0) and 52 <= last['RSI'] <= 64:
                    # فلتر الفريم الأكبر
                    bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)
                    df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_50 = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                    
                    if df_4h['c'].iloc[-1] > ema_50:
                        msg = (f"🏇 **إشارة انفجار (Spot)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"📥 دخول: `{current_price:.4f}`\n"
                               f"🎯 هدف (6%): `{current_price*1.06:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

# --- وظيفة الإبقاء على السيرفر حياً (Keep Alive) ---
def keep_alive():
    while True:
        if APP_URL:
            try:
                requests.get(APP_URL, timeout=10)
                logger.info("📡 تم إرسال Ping ذاتي للإبقاء على السيرفر حياً.")
            except: pass
        time.sleep(600) # كل 10 دقائق

# تشغيل المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

# تشغيل خيط (Thread) الـ Keep Alive
threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def home(): 
    return "🚀 Fast Lane Bot is Running 24/7"

if __name__ == "__main__":
    send_telegram("✅ البوت نشط الآن ومحمي من التوقف.")
    scan_market()
    # جلب المنفذ ديناميكياً لـ Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
