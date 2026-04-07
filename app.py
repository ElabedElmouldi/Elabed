import ccxt
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية (v4.9.5 - تحديث إدارة المخاطر) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v495.json"
RENDER_URL = "https://elabed.onrender.com" 

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'
TF_SLOW = '15m'

# --- إعدادات المحفظة المعدلة ---
INITIAL_BALANCE = 1000.0   # رأس المال: 1000 دولار
TRADE_AMOUNT_USD = 50.0    # قيمة كل صفقة: 50 دولاراً
MAX_VIRTUAL_TRADES = 10    # زيادة عدد الصفقات المسموحة لملء المحفظة (اختياري)

# --- إعدادات التتبع والوقف ---
STOP_LOSS_PCT = 0.02      # وقف خسارة ثابت -2%
ACTIVATION_PCT = 0.03    # تفعيل التتبع عند ربح +3%
CALLBACK_PCT = 0.02      # الخروج عند هبوط 2% من القمة

STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
virtual_trades = {}
virtual_balance = INITIAL_BALANCE
closed_this_hour = [] 
last_report_time = datetime.now()

def load_data():
    global virtual_balance, virtual_trades
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', INITIAL_BALANCE)
                virtual_trades = data.get('virtual_trades', {})
        except: pass

def save_data():
    try:
        data = {'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades}
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. نظام التقارير الساعية ---
def hourly_report_manager():
    global last_report_time, closed_this_hour
    while True:
        try:
            now = datetime.now()
            if now >= last_report_time + timedelta(hours=1):
                open_list = "".join([f"• `{s}` (دخول: `{t['entry']}`)\n" for s, t in virtual_trades.items()]) or "_لا توجد صفقات حالية_"
                closed_list = "".join([f"• `{c['symbol']}`: `{c['pnl_pct']:+.2f}%` ({c['pnl_usd']:+.2f}$)\n" for c in closed_this_hour]) or "_لم تُغلق صفقات_"
                
                report = (
                    f"📊 *تقرير الساعة المنقضية*\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"💰 *إجمالي المحفظة:* `{virtual_balance:.2f} USD`\n"
                    f"📂 *الصفقات المفتوحة:*\n{open_list}\n"
                    f"✅ *نتائج الساعة:*\n{closed_list}\n"
                    f"━━━━━━━━━━━━━━"
                )
                send_telegram(report)
                last_report_time = now
                closed_this_hour = []
                save_data()
        except: pass
        time.sleep(60)

# --- 4. محرك التحليل ---
def analyze_coin(symbol):
    try:
        df_slow = pd.DataFrame(exchange.fetch_ohlcv(symbol, TF_SLOW, limit=20), columns=['t','o','h','l','c','v'])
        if df_slow['c'].iloc[-1] < df_slow['c'].ewm(span=10).mean().iloc[-1]: return None

        df_fast = pd.DataFrame(exchange.fetch_ohlcv(symbol, TF_FAST, limit=20), columns=['t','o
