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

# --- 1. الإعدادات الأساسية (v6.3.0 - شرط الـ 5 قوائم فقط) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v630.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

INITIAL_BALANCE = 1000.0    
TRADE_AMOUNT_USD = 50.0     
MAX_VIRTUAL_TRADES = 20     
STOP_LOSS_PCT = 0.02        # 2%
TAKE_PROFIT_PCT = 0.03      # 3%
SCAN_INTERVAL_MINUTES = 15 

STABLE_AND_GIANTS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDT', 'BTC', 'ETH', 'BNB', 'SOL']

# --- 2. إدارة البيانات والتقارير ---
virtual_trades = {}
virtual_balance = INITIAL_BALANCE
closed_history = [] 

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

# --- 3. محرك التقارير الدورية (ساعي، نصف يومي، يومي) ---
def report_manager():
    last_hourly = datetime.now()
    last_half_day = datetime.now()
    last_daily = datetime.now()

    while True:
        try:
            now = datetime.now()
            
            # تقرير الساعة
            if now >= last_hourly + timedelta(hours=1):
                msg = "🕒 *تقرير الساعة للمحفظة*\n━━━━━━━━━━━━━━\n📂 *المفتوحة:*\n"
                if not virtual_trades: msg += "_لا توجد صفقات حالياً_\n"
                for s, t in virtual_trades.items():
                    try:
                        curr_p = exchange.fetch_ticker(s)['last']
                        move = ((curr_p - t['entry']) / t['entry']) * 100
                        msg += f"• `{s}` | دخل: `{t['start_full_time'].split()[-1]}` | نسبة: `{move:+.2f}%` \n"
                    except: pass
                
                msg += "\n✅ *المغلقة (آخر ساعة):*\n"
                hour_closed = [c for c in closed_history if datetime.strptime(c['close_time'], '%Y-%m-%d %H:%M:%S') >= now - timedelta(hours=1)]
                if not hour_closed: msg += "_لا يوجد_\n"
                for c in hour_closed:
                    msg += f"• `{c['symbol']}` | `{c['pnl_pct']:+.2f}%` | `{c['duration']}`\n"
                
                send_telegram(msg)
                last_hourly = now

            # تقرير نصف يومي و يومي (ملخص الرصيد)
            if now >= last_half_day + timedelta(hours=12):
                send_telegram(f"🌗 *تقرير 12 ساعة*\n💰 الرصيد: `{virtual_balance:.2f}$` | صفقات المفتوحة: `{len(virtual_trades)}`")
                last_half_day = now
                
            if now >= last_daily + timedelta(hours=24):
                send_telegram(f"📅 *التقرير اليومي*\n💰 الرصيد النهائي: `{virtual_balance:.2f}$`")
                last_daily = now

        except: pass
        time.sleep(60)

# --- 4. محرك التحليل والمنطق (شرط 5 قوائم فقط) ---
def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, TF_FAST, limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        df['ema'] = df['c'].ewm(span=10).mean()
        delta = df['c'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/(loss + 1e-9))))
        
        score = 0; curr = df['c'].iloc[-1]
        if curr > df['ema'].iloc[-1]: score += 1                # 1. الاتجاه
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1 # 2. السيولة
        if 50 <= rsi.iloc[-1] <= 75: score += 1                 # 3. الزخم
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.45: score += 1 # 4. القفزة
        if curr > df['h'].tail(5).max() * 0.997: score += 1     # 5. الاختراق

        return {'symbol': symbol, 'price': curr, 'score': score}
    except: return None

def radar_engine():
    global virtual_balance
    send_telegram("🚀 *نظام الـ 5 قوائم v6.3.0 نشط*\n(الدخول فقط عند اكتمال الشروط 100%)")
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

            # الفلترة: دخول فقط لمن حقق 5/5
            list_perfect = [r for r in all_results if r['score'] == 5]

            for res in list_perfect:
                if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    if virtual_balance >= TRADE_AMOUNT_USD:
                        now = datetime.now()
                        virtual_trades[res['symbol']] = {
                            'entry': res['price'],
                            'start_full_time': now.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        virtual_balance -= TRADE_AMOUNT_USD
                        save_data()
                        
                        # إشعار دخول تفصيلي
                        msg = (f"🔥 *دخول ذهبي (5/5)*\n🪙 `{res['symbol']}`\n💰 السعر: `{res['price']}`\n"
                               f"🛑 الوقف: `{res['price']*0.98:.6f}`\n🎯 الهدف: `{res['price']*1.03:.6f}`")
                        send_telegram(msg)

            send_telegram(f"✅ تم المسح. القادمة: {(cycle_start + timedelta(minutes=SCAN_INTERVAL_MINUTES)).strftime('%H:%M')}")
        except: pass
        elapsed = (datetime.now() - cycle_start).total_seconds()
        time.sleep(max(1, (SCAN_INTERVAL_MINUTES * 60) - elapsed))

# --- 5. مراقبة وإغلاق الصفقات ---
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
                    duration = str(now - datetime.strptime(trade['start_full_time'], '%Y-%m-%d %H:%M:%S')).split('.')[0]
                    virtual_balance += (TRADE
