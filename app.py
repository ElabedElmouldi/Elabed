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

# --- 1. الإعدادات الأساسية (v6.2.0 - نظام التقارير المتقدم) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v620.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

INITIAL_BALANCE = 1000.0    
TRADE_AMOUNT_USD = 50.0     
MAX_VIRTUAL_TRADES = 20     
STOP_LOSS_PCT = 0.02        
TAKE_PROFIT_PCT = 0.03      
SCAN_INTERVAL_MINUTES = 15 

STABLE_AND_GIANTS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDT', 'BTC', 'ETH', 'BNB', 'SOL']

# --- 2. إدارة البيانات والتقارير ---
virtual_trades = {}
virtual_balance = INITIAL_BALANCE
closed_history = [] # سجل الصفقات المغلقة للتقارير

def load_data():
    global virtual_balance, virtual_trades, closed_history
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', INITIAL_BALANCE)
                virtual_trades = data.get('virtual_trades', {})
                closed_history = data.get('closed_history', [])
        except: pass

def save_data():
    try:
        data = {
            'virtual_balance': virtual_balance, 
            'virtual_trades': virtual_trades,
            'closed_history': closed_history
        }
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

# --- 3. محرك التقارير الدورية ---
def report_manager():
    last_hourly = datetime.now()
    last_half_day = datetime.now()
    last_daily = datetime.now()

    while True:
        try:
            now = datetime.now()
            
            # --- أ. تقرير كل ساعة ---
            if now >= last_hourly + timedelta(hours=1):
                msg = "🕒 *تقرير الساعة للمحفظة*\n"
                msg += "━━━━━━━━━━━━━━\n"
                
                # الصفقات المفتوحة
                msg += "📂 *المفتوحة:*\n"
                if not virtual_trades: msg += "_لا توجد صفقات حالياً_\n"
                for s, t in virtual_trades.items():
                    try:
                        curr_p = exchange.fetch_ticker(s)['last']
                        move = ((curr_p - t['entry']) / t['entry']) * 100
                        msg += f"• `{s}` | دخل: `{t['start_full_time'].split()[-1]}` | نسبة: `{move:+.2f}%` \n"
                    except: pass
                
                # الصفقات المغلقة في آخر ساعة
                msg += "\n✅ *المغلقة (آخر ساعة):*\n"
                hour_closed = [c for c in closed_history if datetime.strptime(c['close_time'], '%Y-%m-%d %H:%M:%S') >= now - timedelta(hours=1)]
                if not hour_closed: msg += "_لم تغلق أي صفقة_\n"
                for c in hour_closed:
                    msg += f"• `{c['symbol']}` | نتيجة: `{c['pnl_pct']:+.2f}%` | مدة: `{c['duration']}`\n"
                
                send_telegram(msg)
                last_hourly = now

            # --- ب. تقرير نصف يومي (12 ساعة) ---
            if now >= last_half_day + timedelta(hours=12):
                half_closed = [c for c in closed_history if datetime.strptime(c['close_time'], '%Y-%m-%d %H:%M:%S') >= now - timedelta(hours=12)]
                total_pnl = sum([c['pnl_pct'] for c in half_closed])
                msg = f"🌗 *تقرير نصف يومي (12 ساعة)*\n━━━━━━━━━━━━━━\n"
                msg += f"📊 عدد الصفقات المغلقة: `{len(half_closed)}` \n"
                msg += f"📈 إجمالي الربح/الخسارة: `{total_pnl:+.2f}%` \n"
                msg += f"💰 قيمة المحفظة: `{virtual_balance:.2f}$`"
                send_telegram(msg)
                last_half_day = now

            # --- ج. تقرير يومي (24 ساعة) ---
            if now >= last_daily + timedelta(hours=24):
                daily_closed = [c for c in closed_history if datetime.strptime(c['close_time'], '%Y-%m-%d %H:%M:%S') >= now - timedelta(hours=24)]
                total_pnl = sum([c['pnl_pct'] for c in daily_closed])
                msg = f"📅 *التقرير اليومي الشامل*\n━━━━━━━━━━━━━━\n"
                msg += f"📉 صفقات اليوم: `{len(daily_closed)}` \n"
                msg += f"🏆 أداء اليوم: `{total_pnl:+.2f}%` \n"
                msg += f"💰 المحفظة النهائية: `{virtual_balance:.2f}$`"
                send_telegram(msg)
                last_daily = now
                
                # تنظيف السجل القديم (اختياري)
                if len(closed_history) > 100: closed_history[:] = closed_history[-100:]

        except Exception as e: print(f"Report Error: {e}")
        time.sleep(60)

# --- 4. محرك التحليل والمراقبة (v6.1.0) ---
def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, TF_FAST, limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        df['ema'] = df['c'].ewm(span=10).mean()
        delta = df['c'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/(loss + 1e-9))))
        score = 0; curr = df['c'].iloc[-1]
        if curr > df['ema'].iloc[-1]: score += 1
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1
        if 50 <= rsi.iloc[-1] <= 75: score += 1
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.45: score += 1
        if curr > df['h'].tail(5).max() * 0.997: score += 1
        return {'symbol': symbol, 'price': curr, 'score': score}
    except: return None

def radar_engine():
    global virtual_balance
    send_telegram("📊 *بدء نظام التقارير المتكامل v6.2.0*")
    while True:
        cycle_start = datetime.now()
        try:
            tickers = exchange.fetch_tickers()
            all_targets = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_AND_GIANTS]
            sorted_targets = sorted(all_targets, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:600]
            chunks = [sorted_targets[i:i + 150] for i in range(0, len(sorted_targets), 150)]
            all_results = []
            for chunk in chunks:
                with ThreadPoolExecutor(max_workers=15) as executor:
                    batch_results = list(filter(None, executor.map(analyze_coin, chunk)))
                    all_results.extend(batch_results)
                time.sleep(1)
            
            list_top = [r for r in all_results if r['score'] >= 4]
            for res in list_top:
                if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    if virtual_balance >= TRADE_AMOUNT_USD:
                        now = datetime.now()
                        virtual_trades[res['symbol']] = {
                            'entry': res['price'],
                            'start_full_time': now.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        virtual_balance -= TRADE_AMOUNT_USD
                        save_data()
                        send_telegram(f"🚀 *دخول:* `{res['symbol']}` | سعر: `{res['price']}`")
        except: pass
        elapsed = (datetime.now() - cycle_start).total_seconds()
        time.sleep(max(1, (SCAN_INTERVAL_MINUTES * 60) - elapsed))

def monitor_trades():
    global virtual_balance
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                cp = exchange.fetch_ticker(s)['last']
                gain = (cp - trade['entry']) / trade['entry']
                
                if gain >= TAKE_PROFIT_PCT or gain <= -STOP_LOSS_PCT:
                    now = datetime.now()
                    start_dt = datetime.strptime(trade['start_full_time'], '%Y-%m-%d %H:%M:%S')
                    duration = str(now - start_dt).split('.')[0]
                    
                    pnl_val = (TRADE_AMOUNT_USD * (1 + gain))
                    virtual_balance += pnl_val
                    
                    # حفظ في سجل التاريخ للتقارير
                    closed_history.append({
                        'symbol': s, 'pnl_pct': gain * 100, 
                        'duration': duration, 'close_time': now.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                    send_telegram(f"🏁 *إغلاق:* `{s}` | `{gain*100:+.2f}%` | مدة: `{duration}`")
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(5)

# --- 5. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Reporting Bot Active"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    Thread(target=report_manager).start() # تشغيل مدير التقارير
    radar_engine()
