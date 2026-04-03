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

# 1. إعداد السجلات (Logs) لمراقبة الأداء في Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية الأصلية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# رابط التطبيق (اختياري: يفضل وضعه في Environment Variables في Render باسم APP_URL)
APP_URL = os.getenv("APP_URL") 

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

def get_btc_status(exchange):
    """صمام أمان البيتكوين: يمنع العمل في الانهيارات"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        if not bars: return True
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -1.5 
    except: return True

def scan_market():
    logger.info("🏇 جاري فحص 'الخيل السريع' (نطاق السيولة 50-150)...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): 
            logger.info("سوق البيتكوين غير مستقر، تم تخطي الفحص.")
            return

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 1000000]
        
        # ترتيب حسب السيولة واختيار النطاق السريع
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        fast_lane_symbols = sorted_symbols[50:150] 

        for symbol in fast_lane_symbols:
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # حساب الاختراق (Breakout)
                recent_high = df['h'].iloc[-21:-1].max()
                current_price = df['c'].iloc[-1]
                
                # حساب المؤشرات الفنية
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(30).mean()
                
                # حساب RSI
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # شروط الاستراتيجية (الانفجار السعري)
                is_squeezed = last['Width'] < 2.0  
                is_breaking = current_price > recent_high 
                has_huge_volume = last['v'] > (last['Vol_MA'] * 3.0) 
                has_space = 52 <= last['RSI'] <= 64 

                if is_squeezed and is_breaking and has_huge_volume and has_space:
                    # فلتر الفريم الأكبر (4 ساعات)
                    bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)
                    df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_50 = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                    
                    if df_4h['c'].iloc[-1] > ema_50:
                        msg = (f"🏇 **إشارة عملة سريعة (Spot)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"الوضع: انفجار سيولة 3x + اختراق قمة\n\n"
                               f"📥 دخول: `{current_price:.4f}`\n"
                               f"🎯 هدف (6%): `{current_price*1.06:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
                        logger.info(f"إشارة مرسلة لعملة: {symbol}")
            except: continue
    except Exception as e: 
        logger.error(f"خطأ في الفحص: {e}")

# --- وظيفة الإبقاء على السيرفر حياً (Keep Alive) ---
def keep_alive():
    while True:
        if APP_URL:
            try:
                requests.get(APP_URL, timeout=10)
                logger.info("📡 Ping ذاتي ناجح.")
            except: pass
        time.sleep(600) # فحص كل 10 دقائق

# المجدول الزمني (كل 15 دقيقة)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

# تشغيل خيط الـ Keep Alive في الخلفية
threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def home(): 
    return "<h1>Fast Lane Bot v5.2 - Active 24/7</h1>"

if __name__ == "__main__":
    send_telegram("🏇 **تم إعادة تفعيل الرادار بالتوكن الأصلي!**\nالبوت محمي الآن من التوقف التلقائي.")
    scan_market()
    # جلب المنفذ ديناميكياً لبيئة Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
