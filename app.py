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

# --- 1. الإعدادات الأساسية (v4.9.8 - تقرير ساعي + يومي) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v498.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'
TF_SLOW = '15m'

INITIAL_BALANCE = 1000.0   
TRADE_AMOUNT_USD = 50.0    
MAX_VIRTUAL_TRADES = 10    

# إعدادات التتبع
ACTIVATION_PCT = 0.03    
CALLBACK_PCT = 0.02      

STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
virtual_trades = {}
virtual_balance = INITIAL_BALANCE
daily_stats = {"wins": 0, "total_pnl_usd": 0.0, "trades_count": 0} # بيانات التقرير اليومي
last_report_time = datetime.now()
last_daily_report_day = datetime.now().day

def load_data():
    global virtual_balance, virtual_trades, daily_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', INITIAL_BALANCE)
                virtual_trades = data.get('virtual_trades', {})
                daily_stats = data.get('daily_stats', {"wins": 0, "total_pnl_usd": 0.0, "trades_count": 0})
        except: pass

def save_data():
    try:
        data = {
            'virtual_balance': virtual_balance, 
            'virtual_trades': virtual_trades,
            'daily_stats': daily_stats
        }
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. نظام التقارير (ساعي + يومي) ---
def report_manager():
    global last_report_time, last_daily_report_day, daily_stats
    while True:
        try:
            now = datetime.now()
            
            # أ. التقرير الساعي (التفصيلي)
            if now >= last_report_time + timedelta(hours=1):
                report = "📊 *تقرير الساعة المنقضية*\n━━━━━━━━━━━━━━\n"
                if virtual_trades:
                    for symbol, t in virtual_trades.items():
                        try: cp = exchange.fetch_ticker(symbol)['last']
                        except: cp = t['entry']
                        current_gain = ((cp - t['entry']) / t['entry']) * 100
                        report += f"🔸 *{symbol}*: `{cp}` ({current_gain:+.2f}%)\n"
                else: report += "_لا توجد صفقات مفتوحة_\n"
                send_telegram(report)
                last_report_time = now

            # ب. التقرير اليومي (عند تغير اليوم أو الساعة 23:59)
            if now.day != last_daily_report_day:
                daily_msg = (
                    "📅 *التقرير اليومي للملحمة*\n"
                    "━━━━━━━━━━━━━━\n"
                    f"💰 *الرصيد النهائي:* `{virtual_balance:.2f} USD`\n"
                    f"📈 *صافي ربح اليوم:* `{daily_stats['total_pnl_usd']:+.2f} USD`\n"
                    f"✅ *عدد الصفقات المنفذة:* `{daily_stats['trades_count']}`\n"
                    f"🏆 *الرابحة منها:* `{daily_stats['wins']}`\n"
                    "━━━━━━━━━━━━━━"
                )
                send_telegram(daily_msg)
                # تصفير بيانات اليوم الجديد
                daily_stats = {"wins": 0, "total_pnl_usd": 0.0, "trades_count": 0}
                last_daily_report_day = now.day
                save_data()

        except Exception as e: print(f"Report error: {e}")
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

# --- 5. مراقبة الصفقات ---
def monitor_trades():
    global virtual_balance, daily_stats
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                cp = exchange.fetch_ticker(s)['last']
                
                if cp > trade.get('highest_price', 0): virtual_trades[s]['highest_price'] = cp
                if cp < trade.get('lowest_price', trade['entry']): virtual_trades[s]['lowest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drawdown = (trade['highest_price'] - cp) / trade['highest_price'] if trade['highest_price'] > 0 else 0
                
                if gain >= ACTIVATION_PCT or (trade['highest_price']/trade['entry'] - 1) >= ACTIVATION_PCT:
                    if drawdown >= CALLBACK_PCT:
                        pnl_usd = TRADE_AMOUNT_USD * gain
                        virtual_balance += pnl_usd
                        
                        # تحديث الإحصائيات اليومية
                        daily_stats['total_pnl_usd'] += pnl_usd
                        daily_stats['trades_count'] += 1
                        if pnl_usd > 0: daily_stats['wins'] += 1
                        
                        send_telegram(f"✅ *إغلاق صفقة: {s}*\nالربح: `{gain*100:+.2f}%` (`{pnl_usd:+.2f}$`)")
                        del virtual_trades[s]
                        save_data()
            time.sleep(10)
        except: time.sleep(5)

def radar_engine():
    send_telegram("🚀 *بوت الفهد v4.9.8 نشط*\n_تم إضافة التقارير اليومية_")
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
                            'lowest_price': res['price'],
                            'start_time': datetime.now().strftime('%H:%M:%S')
                        }
                        save_data()
                        send_telegram(f"⚡ *دخول:* `{res['symbol']}` بسعر `{res['price']}`")
            time.sleep(30)
        except: time.sleep(20)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Bot Running"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    Thread(target=report_manager).start()
    radar_engine()
