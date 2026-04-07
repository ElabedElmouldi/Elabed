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

# --- 1. الإعدادات (v5.4.1 - ميزانية 1000$ موزعة على 20 صفقة) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v541.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

# إعدادات المحفظة المطلوبة
INITIAL_BALANCE = 1000.0    # القيمة الافتراضية 1000 دولار
TRADE_AMOUNT_USD = 50.0     # قيمة كل صفقة 50 دولار
MAX_VIRTUAL_TRADES = 20     # الحد الأقصى 20 صفقة متزامنة

# أهداف الربح والخسارة
STOP_LOSS_PCT = 0.02        # وقف خسارة عند -2%
TAKE_PROFIT_PCT = 0.03      # جني أرباح عند +3%

MAX_SCAN_LIST = 600
CHUNK_SIZE = 150
current_chunk_index = 0

# استبعاد العملات الثقيلة والمستقرة
STABLE_AND_GIANTS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDT', 'BTC', 'ETH', 'BNB', 'SOL']

# --- 2. إدارة البيانات ---
virtual_trades = {}
closed_trades_history = [] 
virtual_balance = INITIAL_BALANCE
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
    global last_report_time, closed_trades_history
    while True:
        try:
            now = datetime.now()
            if now >= last_report_time + timedelta(hours=1):
                # تقرير الصفقات المفتوحة والمدة
                open_msg = f"📂 *تقرير الصفقات المفتوحة ({len(virtual_trades)}/20)*\n━━━━━━━━━━━━━━\n"
                if virtual_trades:
                    for s, t in virtual_trades.items():
                        start_dt = datetime.strptime(t['start_full_time'], '%Y-%m-%d %H:%M:%S')
                        duration = now - start_dt
                        open_msg += f"🔸 `{s}` | دخول: `{t['entry']}`\n🕒 المدة: `{str(duration).split('.')[0]}`\n┈┈┈┈┈┈┈┈┈┈\n"
                else: open_msg += "_لا توجد صفقات مفتوحة_\n"
                
                # تقرير الصفقات المغلقة
                closed_msg = "\n✅ *تقرير الصفقات المغلقة (آخر ساعة)*\n━━━━━━━━━━━━━━\n"
                if closed_trades_history:
                    for c in closed_trades_history:
                        closed_msg += f"🔹 `{c['symbol']}` | النتيجة: `{c['pnl_pct']:+.2f}%`\n🕒 المدة: `{c['duration']}`\n┈┈┈┈┈┈┈┈┈┈\n"
                else: closed_msg += "_لم تُغلق أي صفقات هذه الساعة_\n"

                send_telegram(open_msg + closed_msg)
                closed_trades_history = []
                last_report_time = now
        except: pass
        time.sleep(60)

# --- 4. محرك التحليل (الاستراتيجيات الخمس) ---
def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, TF_FAST, limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        # RSI حساب
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain/(loss + 1e-9))))
        
        score = 0
        curr = df['c'].iloc[-1]
        
        # تطبيق الفلاتر
        if curr > df['c'].ewm(span=10).mean().iloc[-1]: score += 1
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1
        if 50 <= df['rsi'].iloc[-1] <= 75: score += 1
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.4: score += 1
        if curr > df['h'].tail(5).max() * 0.98: score += 1
        
        if score >= 4: return {'symbol': symbol, 'price': curr}
    except: return None

# --- 5. مراقبة الصفقات ---
def monitor_trades():
    global virtual_balance, closed_trades_history
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                gain = (cp - trade['entry']) / trade['entry']
                
                exit_now = False
                if gain >= TAKE_PROFIT_PCT: exit_now = True
                elif gain <= -STOP_LOSS_PCT: exit_now = True

                if exit_now:
                    now = datetime.now()
                    start_dt = datetime.strptime(trade['start_full_time'], '%Y-%m-%d %H:%M:%S')
                    duration_str = str(now - start_dt).split('.')[0]
                    pnl_usd = TRADE_AMOUNT_USD * gain
                    virtual_balance += pnl_usd
                    
                    closed_trades_history.append({'symbol': s, 'pnl_pct': gain*100, 'duration': duration_str})
                    
                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 العملة: `{s}`\n📊 النتيجة: `{gain*100:+.2f}%` \n🕒 المدة: `{duration_str}`\n💰 الرصيد الحالي: `{virtual_balance:.2f}$`")
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(5)

def radar_engine():
    global current_chunk_index
    send_telegram(f"🚀 *تم التشغيل v5.4.1*\nالميزانية: `1000$` | الصفقات: `20` بـ `50$`")
    while True:
        try:
            tickers = exchange.fetch_tickers()
            all_targets = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_AND_GIANTS]
            sorted_targets = sorted(all_targets, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:MAX_SCAN_LIST]
            
            chunks = [sorted_targets[i:i + CHUNK_SIZE] for i in range(0, len(sorted_targets), CHUNK_SIZE)]
            if not chunks: continue
            if current_chunk_index >= len(chunks): current_chunk_index = 0
            
            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(filter(None, executor.map(analyze_coin, chunks[current_chunk_index])))

            for res in results:
                if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    if virtual_balance >= TRADE_AMOUNT_USD:
                        now = datetime.now()
                        virtual_trades[res['symbol']] = {
                            'entry': res['price'],
                            'start_full_time': now.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        # خصم القيمة وهمياً من الرصيد المتاح لفتح صفقات أخرى
                        virtual_balance -= TRADE_AMOUNT_USD 
                        save_data()
                        
                        send_telegram(
                            f"⚡ *إشعار دخول صفقة ({len(virtual_trades)}/20)*\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"🪙 العملة: `{res['symbol']}`\n"
                            f"💰 السعر: `{res['price']}`\n"
                            f"🎯 الهدف: `+3%` | 🛑 الوقف: `-2%`"
                        )

            current_chunk_index += 1
            time.sleep(20)
        except: time.sleep(20)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return f"Active Trades: {len(virtual_trades)} | Balance: {virtual_balance}"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    Thread(target=hourly_report_manager).start()
    radar_engine()
