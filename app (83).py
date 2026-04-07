import ccxt
import pandas as pd
import numpy as np
import time
import requests
import os  # مهم جداً للإصلاح
from threading import Thread
from flask import Flask
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
# ملاحظة: SERVER_URL سيتم استخراجه تلقائياً أو ضعه هنا
SERVER_URL = os.environ.get("SERVER_URL", "https://your-app-name.onrender.com")

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

# --- 2. محرك المراقبة (التتبع السعري 4% / 2%) ---

def monitor_loop():
    while True:
        try:
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100

                # تفعيل التتبع عند وصول الربح لـ 4%
                if res_pct >= 4.0:
                    if not trade['trailing_active']:
                        trade['trailing_active'] = True
                        send_telegram(f"🎯 *تفعيل التتبع*: `{sym}` رابح `{res_pct:.2f}%` (تحديث كل 10ث)")
                    
                    # تحديث الوقف (فارق 2% عن القمة)
                    new_sl = cp * 0.98
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                    
                    time.sleep(10) # سرعة فائقة عند الربح

                # شرط الإغلاق (الربح أو الوقف)
                if cp >= trade['tp'] or cp <= trade['sl']:
                    final_res = ((cp - trade['entry']) / trade['entry']) * 100
                    status = "✅ Target" if cp >= trade['tp'] else "📉 SL/Trailing"
                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{sym}`\n📊 النتيجة: `{final_res:+.2f}%`\n📝 الحالة: {status}")
                    del active_trades[sym]
            
            time.sleep(20)
        except Exception as e:
            print(f"Monitor Error: {e}")
            time.sleep(10)

# --- 3. الرادار (شرط ربح 4% ووقف 2%) ---

def update_global_cache():
    global hourly_cache, last_hourly_update
    try:
        tickers = exchange.fetch_tickers()
        all_symbols = [s for s in tickers if s.endswith('/USDT') 
                       and s not in ['BTC/USDT', 'ETH/USDT']][:300]
        
        temp_list = []
        for sym in all_symbols:
            try:
                o1 = exchange.fetch_ohlcv(sym, '1h', limit=24)
                df = pd.DataFrame(o1, columns=['t','o','h','l','c','v'])
                mom = ((df['c'].iloc[-1] - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
                if df['c'].iloc[-1] > df['c'].ewm(span=10).mean().iloc[-1]:
                    temp_list.append({'symbol': sym, 'mom': mom, 'high_1h': df['h'].max()})
            except: continue
            
        top_10 = sorted(temp_list, key=lambda x: x['mom'], reverse=True)[:10]
        hourly_cache = {x['symbol']: x for x in top_10}
        last_hourly_update = time.time()
    except: pass

def analyze_symbol(symbol):
    try:
        h_info = hourly_cache.get(symbol)
        o15 = exchange.fetch_ohlcv(symbol, '15m', limit=20)
        df15 = pd.DataFrame(o15, columns=['t','o','h','l','c','v'])
        cp = df15['c'].iloc[-1]
        
        # شرط الاختراق + هدف 4% + وقف 2%
        if cp >= h_info['high_1h']:
            return {'symbol': symbol, 'price': cp, 'tp': cp * 1.04, 'sl': cp * 0.98}
    except: return None

def radar_loop():
    send_telegram("🚀 *Sniper V10.6 PRO Online*\nالوضع: محاكاة (Virtual Mode)\nالشروط: ربح 4% / وقف 2%")
    while True:
        try:
            if time.time() - last_hourly_update > 3600: update_global_cache()
            targets = list(hourly_cache.keys())
            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(analyze_symbol, targets)))
            
            for res in results:
                if res['symbol'] not in active_trades and len(active_trades) < MAX_TRADES:
                    active_trades[res['symbol']] = {
                        'entry': res['price'], 'tp': res['tp'], 'sl': res['sl'], 
                        'start_time': datetime.now(), 'trailing_active': False
                    }
                    send_telegram(f"🆕 *صفقة تجريبية*: `{res['symbol']}`\n💰 دخول: `{res['price']}`\n🎯 هدف: `+4%` | 🛡️ وقف: `-2%` ")
            time.sleep(600)
        except: time.sleep(60)

# --- 4. تشغيل السيرفر (إصلاح Port) ---
@app.route('/')
def health(): return "AI Trader Active", 200

if __name__ == "__main__":
    update_global_cache()
    # تشغيل المهام في الخلفية
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    # نظام الـ Ping للبقاء نشطاً
    Thread(target=lambda: [(requests.get(SERVER_URL), time.sleep(300)) for _ in iter(int, 1)], daemon=True).start()
    
    # الإصلاح البرمجي للبورت ليعمل على Render/Heroku
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
