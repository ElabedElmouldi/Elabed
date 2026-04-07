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

# --- 1. الإعدادات الأساسية (v4.9.6 - إصلاح أخطاء الصيغة) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v496.json"
RENDER_URL = "https://elabed.onrender.com" 

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'
TF_SLOW = '15m'

# إعدادات المحفظة
INITIAL_BALANCE = 1000.0   
TRADE_AMOUNT_USD = 50.0    
MAX_VIRTUAL_TRADES = 10    

# إعدادات التتبع
STOP_LOSS_PCT = 0.02      
ACTIVATION_PCT = 0.03    
CALLBACK_PCT = 0.02      

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
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. نظام التقارير الساعية ---
def hourly_report_manager():
    global last_report_time, closed_this_hour
    while True:
        try:
            now = datetime.now()
            if now >= last_report_time + timedelta(hours=1):
                open_list = ""
                for s, t in virtual_trades.items():
                    open_list += f"• `{s}` (دخول: `{t['entry']}`)\n"
                if not open_list: open_list = "_لا توجد صفقات حالية_"

                closed_list = ""
                for c in closed_this_hour:
                    closed_list += f"• `{c['symbol']}`: `{c['pnl_pct']:+.2f}%` (`{c['pnl_usd']:+.2f}$`)\n"
                if not closed_list: closed_list = "_لم تُغلق صفقات_"
                
                report = (
                    "📊 *تقرير الساعة المنقضية*\n"
                    "━━━━━━━━━━━━━━\n"
                    f"💰 *المحفظة:* `{virtual_balance:.2f} USD`\n"
                    f"📂 *المفتوحة:*\n{open_list}\n"
                    f"✅ *نتائج الساعة:*\n{closed_list}\n"
                    "━━━━━━━━━━━━━━"
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
        bars_slow = exchange.fetch_ohlcv(symbol, TF_SLOW, limit=20)
        df_slow = pd.DataFrame(bars_slow, columns=['t','o','h','l','c','v'])
        if df_slow['c'].iloc[-1] < df_slow['c'].ewm(span=10).mean().iloc[-1]: return None

        bars_fast = exchange.fetch_ohlcv(symbol, TF_FAST, limit=20)
        df_fast = pd.DataFrame(bars_fast, columns=['t','o','h','l','c','v'])
        if df_fast['v'].iloc[-1] > (df_fast['v'].tail(10).mean() * 2.5):
            jump = ((df_fast['c'].iloc[-1] - df_fast['c'].iloc[-2]) / df_fast['c'].iloc[-2]) * 100
            if jump > 0.2: return {'symbol': symbol, 'price': df_fast['c'].iloc[-1]}
    except: return None

# --- 5. مراقبة الصفقات (كل 10 ثواني) ---
def monitor_trades():
    global virtual_balance, closed_this_hour
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                
                if cp > trade.get('highest_price', 0):
                    virtual_trades[s]['highest_price'] = cp
                
                entry_p = trade['entry']
                highest_p = virtual_trades[s]['highest_price']
                gain = (cp - entry_p) / entry_p
                drawdown = (highest_p - cp) / highest_p if highest_p > 0 else 0
                
                exit_now = False
                reason = ""

                if gain <= -STOP_LOSS_PCT:
                    exit_now = True
                    reason = "Stop Loss (-2%)"
                elif gain >= ACTIVATION_PCT or (highest_p/entry_p - 1) >= ACTIVATION_PCT:
                    if drawdown >= CALLBACK_PCT:
                        exit_now = True
                        reason = f"Trailing Exit ({gain*100:+.2f}%)"

                if exit_now:
                    pnl_usd = TRADE_AMOUNT_USD * gain
                    virtual_balance += pnl_usd
                    closed_this_hour.append({'symbol': s, 'pnl_pct': gain*100, 'pnl_usd': pnl_usd})
                    
                    msg = (
                        f"🏁 *إشعار خروج*\n"
                        f"🪙 العملة: `{s}`\n"
                        f"📈 النتيجة: `{gain*100:+.2f}%`\n"
                        f"💵 الربح: `{pnl_usd:+.2f} USD`\n"
                        f"سبب: `{reason}`"
                    )
                    send_telegram(msg)
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(5)

def radar_engine():
    send_telegram(f"🚀 *v4.9.6 نشط*\nالمحفظة: `{virtual_balance}$` | الصفقة: `50$`")
    while True:
        try:
            tickers = exchange.fetch_tickers()
            targets = sorted([s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS], 
                            key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:60]

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(filter(None, executor.map(analyze_coin, targets)))

            for res in results:
                if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    if virtual_balance >= TRADE_AMOUNT_USD:
                        virtual_trades[res['symbol']] = {
                            'entry': res['price'], 
                            'highest_price': res['price'],
                            'start_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        save_data()
                        send_telegram(f"⚡ *دخول:* `{res['symbol']}`\n💰 السعر: `{res['price']}`\n💵 القيمة: `50$`")
            time.sleep(30)
        except: time.sleep(20)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return f"Active Trades: {len(virtual_trades)}"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    Thread(target=hourly_report_manager).start()
    radar_engine()
