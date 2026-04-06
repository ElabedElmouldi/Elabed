import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({
    'apiKey': os.environ.get('BINANCE_API_KEY', ''),
    'secret': os.environ.get('BINANCE_SECRET', ''),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# --- إعداداتك الجديدة ---
MAX_TRADES = 20            # الدخول في 20 عملة
TRADE_AMOUNT_USD = 10.0    # كل عملة بـ 10 دولار
SCAN_INTERVAL = 300        # مسح كل 5 دقائق
ACTIVATION_PROFIT = 0.03   # تتبع عند 3%
TRAILING_GAP = 0.015       # فارق 1.5%

active_trades = {}
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك الفلترة (نظام الـ 20 شرطاً) ---
def get_breakout_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]; score = 0
        
        # المتوسطات والسيولة
        ema20 = df['c'].ewm(span=20).mean(); avg_v = df['v'].tail(20).mean()
        
        # تطبيق شروط الانفجار
        if cp > ema20.iloc[-1]: score += 2
        if df['v'].iloc[-1] > avg_v * 2: score += 5
        if cp > df['h'].iloc[-2]: score += 3
        if cp > df['o'].iloc[-1]: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 3
        if ((cp - df['o'].iloc[-1])/df['o'].iloc[-1]) > 0.006: score += 5
        
        return score, cp
    except: return 0, 0

# --- 3. مراقبة التتبع اللحظي ---
def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; tr = active_trades[s]
                if cp > tr.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                
                gain = (cp - tr['entry']) / tr['entry']
                drop = (active_trades[s]['highest_price'] - cp) / active_trades[s]['highest_price']
                
                if gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP:
                    send_telegram(f"💰 *جني أرباح:* `{s}`\nالنتيجة: `{gain*100:+.2f}%` ")
                    del active_trades[s]
                elif gain <= -0.04: # وقف خسارة حماية
                    send_telegram(f"🛑 *وقف خسارة:* `{s}`\nالنتيجة: `-4%` ")
                    del active_trades[s]
            time.sleep(10)
        except: time.sleep(5)

# --- 4. المحرك الرئيسي (المسح والترتيب) ---
def main_engine():
    send_telegram(f"🛡️ *تشغيل v70.0*\n🎯 الهدف: 20 صفقة × 10$\n📡 مسح 500 عملة / 5 دقائق")
    last_scan = datetime.now() - timedelta(minutes=10)

    while True:
        try:
            now = datetime.now()
            if now >= last_scan + timedelta(seconds=SCAN_INTERVAL):
                # جلب البيانات والترتيب حسب السيولة
                markets = exchange.fetch_markets()
                all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
                tickers = exchange.fetch_tickers(all_usdt)
                targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[20:520]

                # تحليل متوازي لـ 500 عملة
                with ThreadPoolExecutor(max_workers=15) as executor:
                    results = [r for r in list(executor.map(lambda s: {'s':s, 'res':get_breakout_score(s)}, targets)) if r['res'][0] >= 10]

                # ترتيب النتائج حسب السكور (الأعلى أولاً)
                results.sort(key=lambda x: x['res'][0], reverse=True)
                
                # إرسال قائمة أفضل 5
                if results:
                    top_5_msg = "🔝 *أفضل 5 عملات في هذا المسح:*\n"
                    for i, res in enumerate(results[:5]):
                        top_5
