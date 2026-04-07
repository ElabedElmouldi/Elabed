import ccxt
import pandas as pd
import time
import json
import os
from datetime import datetime
from flask import Flask
from threading import Thread
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات العامة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v422.json"
RENDER_URL = "https://your-app-name.onrender.com" # <--- ضع رابط السيرفر الخاص بك هنا

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'
TF_SLOW = '15m'
SCAN_INTERVAL = 30 
MAX_VIRTUAL_TRADES = 5
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات (تحميل وحفظ) ---
virtual_trades = {}
virtual_balance = 1000.0
daily_pnl_usd = 0.0
last_reset_date = str(datetime.now().date())

def load_data():
    global virtual_balance, virtual_trades, daily_pnl_usd, last_reset_date
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', 1000.0)
                virtual_trades = data.get('virtual_trades', {})
                daily_pnl_usd = data.get('daily_pnl_usd', 0.0)
                last_reset_date = data.get('last_reset_date', str(datetime.now().date()))
        except: pass

def save_data():
    try:
        data = { 'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades,
                 'daily_pnl_usd': daily_pnl_usd, 'last_reset_date': last_reset_date }
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. وظيفة منع النوم (Keep Alive) ---
def keep_alive_ping():
    """ترسل طلباً للسيرفر كل 5 دقائق لمنع الاستضافة من النوم"""
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
            print(f"[{datetime.now()}] Ping sent to {RENDER_URL} to keep alive.")
        except Exception as e:
            print(f"Ping failed: {e}")
        time.sleep(300) # 300 ثانية = 5 دقائق

# --- 4. محرك التحليل المزدوج (Multi-TF Analysis) ---
def fetch_df(symbol, tf, limit=50):
    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    return pd.DataFrame(bars, columns=['t','o','h','l','c','v'])

def analyze_coin(symbol):
    try:
        # 1. تحليل الإطار البطيء (الجودة)
        df_slow = fetch_df(symbol, TF_SLOW, limit=30)
        ema_slow = df_slow['c'].ewm(span=20).mean().iloc[-1]
        current_price = df_slow['c'].iloc[-1]
        
        if current_price <= ema_slow: return None

        # 2. تحليل الإطار السريع (السرعة)
        df_fast = fetch_df(symbol, TF_FAST, limit=30)
        vol_spike = df_fast['v'].iloc[-1] > (df_fast['v'].tail(10).mean() * 2.5)
        fast_change = ((df_fast['c'].iloc[-1] - df_fast['c'].iloc[-2]) / df_fast['c'].iloc[-2]) * 100
        
        score = (fast_change * 10) + (15 if vol_spike else 0)
        
        return {
            'symbol': symbol,
            'score': round(score, 2),
            'price': current_price,
            'is_ready': vol_spike and fast_change > 0.3
        }
    except: return None

# --- 5. الرصد والمراقبة ---
def monitor_trades():
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s); cp = ticker['last']
                if cp > trade.get('highest_price', 0): virtual_trades[s]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drop = (virtual_trades[s]['highest_price'] - cp) / virtual_trades[s]['highest_price']
                
                if gain <= -0.012: exit_reason = "Stop Loss"
                elif gain >= 0.025 and drop >= 0.007: exit_reason = "Trailing TP"
                else: continue
                
                send_telegram(f"🏁 *إغلاق:* `{s}`\n📈 النتيجة: `{gain*100:+.2f}%`")
                del virtual_trades[s]; save_data()
            time.sleep(10)
        except: time.sleep(10)

def radar_engine():
    global daily_pnl_usd, last_reset_date
    send_telegram("🚀 *رادار التوازن v422 نشط*\nتحليل: `1m` (سرعة) + `15m` (جودة)\nنظام Keep-Alive: `Active`")
    
    while True:
        try:
            if last_reset_date != str(datetime.now().date()):
                daily_pnl_usd = 0.0; last_reset_date = str(datetime.now().date()); save_data()

            tickers = exchange.fetch_tickers()
            targets = sorted([s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS], 
                            key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:100]

            with ThreadPoolExecutor(max_workers=15) as executor: # خفض عدد الخيوط قليلاً لراحة السيرفر
                results = list(filter(None, executor.map(analyze_coin, targets)))

            hot_list = sorted(results, key=lambda x: x['score'], reverse=True)[:5]
            
            for coin in hot_list:
                if coin['is_ready'] and coin['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    virtual_trades[coin['symbol']] = {
                        'entry': coin['price'], 'highest_price': coin['price'],
                        'start_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    save_data()
                    send_telegram(f"⚡ *إشارة دخول ذكية*\n🪙 `{coin['symbol']}`\n📊 سكور: `{coin['score']}`")
            
            time.sleep(SCAN_INTERVAL)
        except: time.sleep(20)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Multi-TF Gold Running (Keep-Alive Active)"

if __name__ == "__main__":
    load_data()
    # تشغيل Flask للسيرفر
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    # تشغيل مراقب الصفقات
    Thread(target=monitor_trades).start()
    # تشغيل وظيفة الـ Ping (الجديدة)
    Thread(target=keep_alive_ping).start()
    # تشغيل المحرك الأساسي
    radar_engine()
