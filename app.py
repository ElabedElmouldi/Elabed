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

# --- 1. الإعدادات الأساسية (v6.1.0 - دخول 4 أو 5 قوائم) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v610.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

INITIAL_BALANCE = 1000.0    
TRADE_AMOUNT_USD = 50.0     
MAX_VIRTUAL_TRADES = 20     
STOP_LOSS_PCT = 0.02        # 2%
TAKE_PROFIT_PCT = 0.03      # 3%
SCAN_INTERVAL_MINUTES = 15 

STABLE_AND_GIANTS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDT', 'BTC', 'ETH', 'BNB', 'SOL']

# --- 2. إدارة البيانات ---
virtual_trades = {}
virtual_balance = INITIAL_BALANCE

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

# --- 3. محرك التحليل (الاستراتيجيات الخمس) ---
def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, TF_FAST, limit=50)
        if not bars: return None
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        df['ema'] = df['c'].ewm(span=10).mean()
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/(loss + 1e-9))))
        
        score = 0
        curr = df['c'].iloc[-1]
        
        # القوائم الخمس
        if curr > df['ema'].iloc[-1]: score += 1                # 1. الاتجاه
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1 # 2. السيولة
        if 50 <= rsi.iloc[-1] <= 75: score += 1                 # 3. الزخم
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.45: score += 1 # 4. القفزة
        if curr > df['h'].tail(5).max() * 0.997: score += 1     # 5. الاختراق

        return {'symbol': symbol, 'price': curr, 'score': score}
    except: return None

# --- 4. رادار المسح الدوري (15 دقيقة) ---
def radar_engine():
    global virtual_balance
    send_telegram(f"⚖️ *نظام المسح v6.1.0 نشط*\nالشرط: 4 أو 5 قوائم للدخول\nإعادة المسح: كل {SCAN_INTERVAL_MINUTES} دقيقة")
    
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

            # تصفية العملات (4 أو 5 قوائم)
            list_top = [r for r in all_results if r['score'] >= 4]

            if list_top:
                # إرسال تقرير بالعملات المكتشفة قبل الدخول
                report_msg = "🔍 *عملات قوية مكتشفة (4-5 قوائم):*\n"
                for r in list_top:
                    report_msg += f"• `{r['symbol']}` (النقاط: {r['score']}/5)\n"
                send_telegram(report_msg)

                for res in list_top:
                    # منع التكرار والتحقق من الرصيد والحد الأقصى للصفقات
                    if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                        if virtual_balance >= TRADE_AMOUNT_USD:
                            now = datetime.now()
                            sl_price = res['price'] * (1 - STOP_LOSS_PCT)
                            tp_price = res['price'] * (1 + TAKE_PROFIT_PCT)
                            
                            virtual_trades[res['symbol']] = {
                                'entry': res['price'],
                                'start_full_time': now.strftime('%Y-%m-%d %H:%M:%S')
                            }
                            virtual_balance -= TRADE_AMOUNT_USD
                            save_data()
                            
                            # إشعار الدخول التفصيلي
                            entry_msg = (
                                f"🚀 *إشعار دخول صفقة ({res['score']} قوائم)*\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"🪙 العملة: `{res['symbol']}`\n"
                                f"💰 سعر الدخول: `{res['price']}`\n"
                                f"🛑 وقف الخسارة: `{sl_price:.6f}`\n"
                                f"🎯 جني الأرباح: `{tp_price:.6f}`\n"
                                f"⏰ الوقت: `{now.strftime('%H:%M:%S')}`"
                            )
                            send_telegram(entry_msg)

            send_telegram(f"✅ انتهى مسح 600 عملة. الدورة القادمة: {(cycle_start + timedelta(minutes=SCAN_INTERVAL_MINUTES)).strftime('%H:%M')}")

        except Exception as e:
            print(f"Radar Error: {e}")
        
        elapsed = (datetime.now() - cycle_start).total_seconds()
        wait_time = max(1, (SCAN_INTERVAL_MINUTES * 60) - elapsed)
        time.sleep(wait_time)

# --- 5. مراقبة وإغلاق الصفقات ---
def monitor_trades():
    global virtual_balance
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                gain = (cp - trade['entry']) / trade['entry']
                
                if gain >= TAKE_PROFIT_PCT or gain <= -STOP_LOSS_PCT:
                    virtual_balance += (TRADE_AMOUNT_USD * (1 + gain))
                    res_status = "✅ ربح" if gain > 0 else "❌ خسارة"
                    send_telegram(f"🏁 *إغلاق صفقة:* `{s}`\n📊 النتيجة: `{gain*100:+.2f}%` ({res_status})\n💰 الرصيد: `{virtual_balance:.2f}$`")
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(5)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Bot v6.1.0 Running"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    radar_engine()
