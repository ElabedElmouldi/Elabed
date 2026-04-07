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

# --- 1. الإعدادات (v4.7.0 - تحديث الإشعارات والأهداف) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v470.json"
RENDER_URL = "https://elabed.onrender.com" 

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'
TF_SLOW = '15m'

SCAN_INTERVAL = 30 
MAX_VIRTUAL_TRADES = 5

# --- الأهداف الجديدة ---
STOP_LOSS_PCT = 0.03    # وقف خسارة 3%
TAKE_PROFIT_PCT = 0.03  # جني أرباح 3%

STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
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
        data = {
            'virtual_balance': virtual_balance, 
            'virtual_trades': virtual_trades,
            'daily_pnl_usd': daily_pnl_usd, 
            'last_reset_date': last_reset_date
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. الأنظمة المساعدة ---
def keep_alive_ping():
    while True:
        try: requests.get(RENDER_URL, timeout=10)
        except: pass
        time.sleep(300)

def is_market_safe():
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='15m', limit=2)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        btc_change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        return btc_change > -1.2 
    except: return True

# --- 4. محرك التحليل ---
def fetch_df(symbol, tf, limit=50):
    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    return pd.DataFrame(bars, columns=['t','o','h','l','c','v'])

def analyze_coin(symbol):
    try:
        df_slow = fetch_df(symbol, TF_SLOW, limit=20)
        ema10 = df_slow['c'].ewm(span=10).mean().iloc[-1]
        if df_slow['c'].iloc[-1] < ema10: return None

        df_fast = fetch_df(symbol, TF_FAST, limit=20)
        avg_vol = df_fast['v'].tail(10).mean()
        current_vol = df_fast['v'].iloc[-1]
        
        if current_vol > (avg_vol * 2.5):
            price_jump = ((df_fast['c'].iloc[-1] - df_fast['c'].iloc[-2]) / df_fast['c'].iloc[-2]) * 100
            if price_jump > 0.2:
                return {'symbol': symbol, 'price': df_fast['c'].iloc[-1]}
    except: return None

# --- 5. مراقبة الصفقات والإشعارات التفصيلية ---
def monitor_trades():
    global virtual_balance, daily_pnl_usd
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                
                entry_p = trade['entry']
                gain = (cp - entry_p) / entry_p
                
                exit_now = False
                if gain >= TAKE_PROFIT_PCT or gain <= -STOP_LOSS_PCT:
                    exit_now = True

                if exit_now:
                    # حساب مدة الصفقة
                    start_time = datetime.strptime(trade['start_timestamp'], '%Y-%m-%d %H:%M:%S')
                    duration = datetime.now() - start_time
                    hours, remainder = divmod(duration.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    duration_str = f"{duration.days}d {hours}h {minutes}m" if duration.days > 0 else f"{hours}h {minutes}m"

                    pnl = 100 * gain
                    virtual_balance += pnl
                    daily_pnl_usd += pnl
                    
                    # إشعار الخروج التفصيلي
                    exit_msg = (
                        f"🏁 *إشعار خروج من صفقة*\n"
                        f"🪙 العملة: `{s}`\n"
                        f"📈 النتيجة: `{gain*100:+.2f}%`\n"
                        f"⏳ مدة الصفقة: `{duration_str}`"
                    )
                    send_telegram(exit_msg)
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(10)

def radar_engine():
    global daily_pnl_usd, last_reset_date
    send_telegram("🚀 *بوت الذهب v4.7.0 نشط*\nتم تحديث تنسيق الإشعارات والأهداف (3%/3%)")
    
    while True:
        try:
            if not is_market_safe():
                time.sleep(60); continue 

            tickers = exchange.fetch_tickers()
            targets = sorted([s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS], 
                            key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:80]

            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(filter(None, executor.map(analyze_coin, targets)))

            for res in results:
                if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    tp_price = res['price'] * (1 + TAKE_PROFIT_PCT)
                    sl_price = res['price'] * (1 - STOP_LOSS_PCT)
                    
                    virtual_trades[res['symbol']] = {
                        'entry': res['price'], 
                        'start_timestamp': now_str
                    }
                    save_data()
                    
                    # إشعار الدخول التفصيلي
                    entry_msg = (
                        f"⚡ *إشعار دخول صفقة*\n"
                        f"🪙 اسم العملة: `{res['symbol']}`\n"
                        f"💰 سعر الدخول: `{res['price']}`\n"
                        f"🎯
