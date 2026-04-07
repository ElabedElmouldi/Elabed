import ccxt
import pandas as pd
import numpy as np
import time
import requests
import os  # ضروري لجلب إعدادات السيرفر
from threading import Thread
from flask import Flask
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({'enableRateLimit': True})
MAX_TRADES = 5
active_trades = {}
hourly_cache = {}
last_hourly_update = 0

app = Flask(__name__)

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك المراقبة (تتبع 4% / 2%) ---
def monitor_loop():
    while True:
        try:
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100

                if res_pct >= 4.0:
                    trade['trailing_active'] = True
                    new_sl = cp * 0.98
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                    time.sleep(10)

                if cp >= trade['tp'] or cp <= trade['sl']:
                    final_res = ((cp - trade['entry']) / trade['entry']) * 100
                    send_telegram(f"🏁 *إغلاق*: `{sym}` | النتيجة: `{final_res:+.2f}%` ")
                    del active_trades[sym]
            time.sleep(20)
        except: time.sleep(10)

# --- الرادار والتحليل ---
def update_global_cache():
    global hourly_cache, last_hourly_update
    try:
        tickers = exchange.fetch_tickers()
        all_symbols = [s for s in tickers if s.endswith('/USDT')][:200]
        temp_list = []
        for sym in all_symbols:
            try:
                o1 = exchange.fetch_ohlcv(sym, '1h', limit=24)
                df = pd.DataFrame(o1, columns=['t','o','h','l','c','v'])
                mom = ((df['c'].iloc[-1] - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
                if df['c'].iloc[-1] > df['c'].ewm(span=10).mean().iloc[-1]:
                    temp_list.append({'symbol': sym, 'mom': mom, 'high_1h': df['h'].max()})
            except: continue
        hourly_cache = {x['symbol']: x for x in sorted(temp_list, key=lambda x: x['mom'], reverse=True)[:10]}
        last_hourly_update = time.time()
    except: pass

def radar_loop():
    send_telegram("🚀 *Sniper V10.7 Started*")
    while True:
        try:
            if time.time() - last_hourly_update > 3600: update_global_cache()
            for sym in list(hourly_cache.keys()):
                h_info = hourly_cache[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                if cp >= h_info['high_1h'] and sym not in active_trades and len(active_trades) < MAX_TRADES:
                    active_trades[sym] = {'entry': cp, 'tp': cp * 1.04, 'sl': cp * 0.98, 'trailing_active': False}
                    send_telegram(f"🆕 *دخول*: `{sym}` | هدف: `+4%` | وقف: `-2%` ")
            time.sleep(600)
        except: time.sleep(60)

@app.route('/')
def health(): return "Active", 200

if __name__ == "__main__":
    update_global_cache()
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    
    # القيمة PORT يتم جلبها آلياً من Render/Heroku
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
