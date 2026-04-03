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

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
APP_URL = os.getenv("APP_URL") 

# قائمة الاستبعاد (العملات القيادية والمستقرة)
EXCLUDED_COINS = [
    'BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'DAI/USDT', 
    'TUSD/USDT', 'FDUSD/USDT', 'BUSD/USDT', 'USDP/USDT', 'WBTC/USDT'
]

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
        return change > -2.5 
    except: return True

def scan_market():
    # تسجيل بداية الفحص في Logs الخاص بـ Render
    logger.info("🕒 بدأ الفحص الدوري (كل 15 دقيقة) لـ 300 عملة...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): 
            logger.info("السوق هابط جداً، تم إلغاء دورة الفحص الحالية.")
            return

        tickers = exchange.fetch_tickers()
        
        # تصفية العملات
        symbols = []
        for s in tickers:
            if s.endswith('/USDT'):
                if s not in EXCLUDED_COINS and 'UP/' not in s and 'DOWN/' not in s:
                    if (tickers[s].get('quoteVolume') or 0) > 500000:
                        symbols.append(s)
        
        # اختيار أفضل 300 عملة سيولة
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        target_symbols = sorted_symbols[:300] 

        for symbol in target_symbols:
            try:
                # فحص فريم 15 دقيقة
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                recent_high = df['h'].iloc[-16:-1].max()
                current_price = df['c'].iloc[-1]
                
                # المؤشرات
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100 
                df['Vol_MA'] = df['v'].rolling(20).mean() 
                
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # الشروط (حساسية متوسطة لاصطياد الفرص)
                if current_price >= recent_high and last['v'] > (last['Vol_MA'] * 1.8) and last['Width'] < 5.0 and 50 <= last['RSI'] <= 75:
                    # تأكيد على فريم الساعة
                    bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=30)
                    df_1h = pd.DataFrame(bars_1h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_20 = df_1h['c'].ewm(span=20, adjust=False).mean().iloc[-1]
                    
                    if current_price > ema_20:
                        msg = (f"🚀 **إشارة انفجار (كل 15 دقيقة)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"💰 السعر: `{current_price:.4f}`\n"
                               f"📈 الهدف (5%): `{current_price*1.05:.4f}`\n"
                               f"🛑 الوقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
                        time.sleep(0.5) # حماية من الـ Spam
            except: continue
        logger.info("✅ انتهى فحص الـ 300 عملة بنجاح.")
    except Exception as e: logger.error(f"خطأ في الفحص: {e}")

def keep_alive():
    """وظيفة منع السيرفر من النوم"""
    while True:
        if APP_URL:
            try: requests.get(APP_URL, timeout=10)
            except: pass
        time.sleep(600) # Ping كل 10 دقائق

# ضبط المجدول الزمني ليعمل بدقة كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

# تشغيل منع النوم في الخلفية
threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def home(): 
    return "<h1>Altcoin Radar v5.4 - Running every 15 minutes</h1>"

if __name__ == "__main__":
    send_telegram("✅ البوت مفعل الآن. سيتم فحص 300 عملة كل 15 دقيقة.")
    # الفحص الأول عند التشغيل مباشرة
    scan_market()
    
    # تشغيل السيرفر
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
