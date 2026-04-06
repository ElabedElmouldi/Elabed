import ccxt
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "bot_data.json"
APP_URL = "https://your-app-name.onrender.com" # ⚠️ ضع رابط تطبيقك هنا بعد رفعه

exchange = ccxt.binance({
    'apiKey': os.environ.get('BINANCE_API_KEY', ''),
    'secret': os.environ.get('BINANCE_SECRET', ''),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# الثوابت الفنية
MAX_TRADES = 10
TRADE_AMOUNT_USD = 100.0
SCAN_INTERVAL = 300
STOP_LOSS_PCT = 0.02
ACTIVATION_PROFIT = 0.04
TRAILING_GAP = 0.02

# --- 2. إدارة البيانات والملفات ---
active_trades = {}
wallet_balance = 1000.0

def save_data():
    try:
        data = {'wallet_balance': wallet_balance, 'active_trades': active_trades}
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e: print(f"Error saving: {e}")

def load_data():
    global wallet_balance, active_trades
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                wallet_balance = data.get('wallet_balance', 1000.0)
                active_trades = data.get('active_trades', {})
        except: pass

load_data()

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. نظام منع النوم (Keep-Alive) ---
def keep_alive_ping():
    """دالة تقوم بزيارة رابط السيرفر كل 5 دقائق لمنعه من التوقف"""
    while True:
        try:
            requests.get(APP_URL, timeout=10)
            print("Ping Sent: Server is Awake")
        except: pass
        time.sleep(300) # كل 5 دقائق

# --- 4. خيط المراقبة (10 ثواني) مع تقارير الإغلاق ---
def monitor_thread():
    global wallet_balance
    while True:
        try:
            if not active_trades:
                time.sleep(10); continue
            
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                trade = active_trades[s]
                
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                    # إشعار بداية التتبع
                    if not trade.get('tr_act', False) and ((cp - trade['entry']) / trade['entry']) >= ACTIVATION_PROFIT:
                        active_trades[s]['tr_act'] = True
                        send_telegram(f"🚀 *تنشيط التتبع:* `{s}`\n📈 السعر: `{cp}` (+4%)")
                        save_data()

                highest = active_trades[s]['highest_price']
                gain = (cp - trade['entry']) / trade['entry']
                drop = (highest - cp) / highest
                
                exit_now = False
                if trade.get('tr_act', False) and drop >= TRAILING_GAP:
                    exit_now = True; res = "تتبع الربح 🎯"
                elif not trade.get('tr_act', False) and gain <= -STOP_LOSS_PCT:
                    exit_now = True; res = "وقف الخسارة 🛑"

                if exit_now:
                    # حساب المدة والنتيجة
                    entry_dt = datetime.strptime(trade['entry_time'], '%Y-%m-%d %H:%M:%S')
                    duration = datetime.now() - entry_dt
                    dur_str = f"{duration.seconds // 3600}س و {(duration.seconds % 3600) // 60}د"
                    
                    pnl_usd = TRADE_AMOUNT_USD * gain
                    wallet_balance += pnl_usd
                    
                    msg = (f"🏁 *تقرير نهاية صفقة*\n━━━━━━━━━━━━━━\n"
                           f"🪙 *العملة:* `{s}`\n⏱️ *المدة:* `{dur_str}`\n"
                           f"📈 *النتيجة:* `{gain*100:+.2f}%` (`{pnl_usd:+.2f}$`)\n"
                           f"📝 *السبب:* `{res}`\n━━━━━━━━━━━━━━\n"
                           f"🏦 *المحفظة بعدها:* `{wallet_balance:.2f}$` ")
                    send_telegram(msg)
                    del active_trades[s]
