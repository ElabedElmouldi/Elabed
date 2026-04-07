import ccxt
import pandas as pd
import numpy as np
import time
import requests
import os
from threading import Thread
from flask import Flask
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
SERVER_URL = "https://your-app-name.onrender.com"

exchange = ccxt.binance({'enableRateLimit': True})

MAX_TRADES = 5
COST_PER_TRADE = 100
LOG_FILE = "trading_log.csv"

active_trades = {}
hourly_cache = {}
last_hourly_update = 0

app = Flask(__name__)

# إنشاء ملف السجل إذا لم يكن موجوداً
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=['Symbol', 'Entry_Date', 'Entry_Price', 'Exit_Date', 'Exit_Price', 'Result_Pct', 'Status'])
    df_init.to_csv(LOG_FILE, index=False)

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def log_trade(data):
    """حفظ بيانات الصفقة في ملف CSV"""
    df = pd.read_csv(LOG_FILE)
    df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
    df.to_csv(LOG_FILE, index=False)

# --- 2. محرك المراقبة والتتبع (10 ثوانٍ) ---

def monitor_loop():
    while True:
        try:
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100

                # تفعيل التتبع عند 4% بفارق 2%
                if res_pct >= 4.0:
                    if not trade['trailing_active']:
                        trade['trailing_active'] = True
                        send_telegram(f"🎯 *تفعيل التتبع*: `{sym}` رابح `{res_pct:.2f}%` (تحديث 10ث)")
                    
                    new_sl = cp * 0.98
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                    time.sleep(10)

                # شرط الإغلاق
                if cp >= trade['tp'] or cp <= trade['sl']:
                    final_res = ((cp - trade['entry']) / trade['entry']) * 100
                    status = "🎯 Target" if cp >= trade['tp'] else "🛡️ SL/Trailing"
                    
                    # تسجيل الصفقة
                    log_trade({
                        'Symbol': sym, 'Entry_Date': trade['start_time'], 'Entry_Price': trade['entry'],
                        'Exit_Date': datetime.now().strftime('%Y-%m-%d %H:%M'), 
                        'Exit_Price': cp, 'Result_Pct': f"{final_res:.2f}%", 'Status': status
                    })

                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{sym}`\n📊 النتيجة: `{final_res:+.2f}%`\n📝 الحالة: {status}")
                    del active_trades[sym]
            
            time.sleep(20)
        except: time.sleep(10)

# --- 3. الرادار والتحليل (4% ربح / 2% وقف) ---

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
        
        # شرط الاختراق والفلتر (4% / 2%)
        if cp >= h_info['high_1h']:
            return {'symbol': symbol, 'price': cp, 'tp': cp * 1.04, 'sl': cp * 0.98}
    except: return None

def radar_loop():
    send_telegram("🚀 *V10.5 Ultimate Active*\nنظام المحاكاة + سجل Excel جاهز.")
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
                        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'trailing_active': False
                    }
                    send_telegram(f"🆕 *صفقة تجريبية*: `{res['symbol']}`\n💰 دخول: `{res['price']}`\n🎯 هدف: `+4%` | 🛡️ وقف: `-2%` ")
            time.sleep(600)
        except: time.sleep(60)

# --- 4. التشغيل ---
@app.route('/')
def health(): return "AI Trader V10.5 Online", 200

if __name__ == "__main__":
    update_global_cache()
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    Thread(target=lambda: [(requests.get(SERVER_URL), time.sleep(300)) for _ in iter(int, 1)], daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
