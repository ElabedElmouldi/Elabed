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

# قائمة العملات المستبعدة (العملات القيادية والمستقرة)
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
    """مراقبة حالة البيتكوين العامة"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -2.5 # يسمح بالعمل ما لم ينهار البيتكوين بأكثر من 2.5%
    except: return True

def scan_market():
    logger.info("🔎 بدء فحص 300 عملة بديلة (Altcoins)...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): 
            logger.info("السوق غير مستقر بسبب BTC، تم تأجيل الفحص.")
            return

        tickers = exchange.fetch_tickers()
        
        # --- تصفية العملات الذكية ---
        symbols = []
        for s in tickers:
            if s.endswith('/USDT'):
                # استبعاد القائمة السوداء + عملات الرافعة المالية + العملات منخفضة السيولة
                if s not in EXCLUDED_COINS and 'UP/' not in s and 'DOWN/' not in s:
                    if (tickers[s].get('quoteVolume') or 0) > 500000: # سيولة لا تقل عن نصف مليون
                        symbols.append(s)
        
        # ترتيب حسب السيولة واختيار أول 300 عملة بديلة
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        target_symbols = sorted_symbols[:300] 

        logger.info(f"تم تحديد {len(target_symbols)} عملة للفحص.")

        for symbol in target_symbols:
            try:
                # جلب بيانات 15 دقيقة
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # حساب الاختراق (Breakout)
                recent_high = df['h'].iloc[-16:-1].max()
                current_price = df['c'].iloc[-1]
                
                # المؤشرات الفنية (إعدادات مرنة)
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100 
                df['Vol_MA'] = df['v'].rolling(20).mean() 
                
                # حساب RSI
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # --- شروط استراتيجية الانفجار السعري ---
                condition_price = current_price >= recent_high
                condition_volume = last['v'] > (last['Vol_MA'] * 2.0) # سيولة ضعفي المتوسط
                condition_squeeze = last['Width'] < 5.0 # تذبذب منضغط وجاهز للانفجار
                condition_rsi = 50 <= last['RSI'] <= 75

                if condition_price and condition_volume and condition_squeeze and condition_rsi:
                    # تأكيد أمان إضافي على فريم الساعة
                    bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=30)
                    df_1h = pd.DataFrame(bars_1h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_20 = df_1h['c'].ewm(span=20, adjust=False).mean().iloc[-1]
                    
                    if current_price > ema_20:
                        msg = (f"🚀 **انفجار عملة بديلة (Altcoin)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n\n"
                               f"💰 السعر: `{current_price:.4f}`\n"
                               f"📊 السيولة: {last['v']/last['Vol_MA']:.1f}x أعلى من المعتاد\n\n"
                               f"🎯 هدف (5%): `{current_price*1.05:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
                        logger.info(f"Signal sent: {symbol}")
                        time.sleep(1) 
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

def keep_alive():
    while True:
        if APP_URL:
            try: requests.get(APP_URL, timeout=10)
            except: pass
        time.sleep(600)

# المجدول (فحص كل 15 دقيقة)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def home(): 
    return "<h1>Fast Lane Bot v5.4 - Scanning 300 Altcoins</h1>"

if __name__ == "__main__":
    send_telegram("✅ تم تحديث الرادار: مسح 300 عملة بديلة (مستبعداً BTC/ETH والعملات المستقرة).")
    scan_market()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
