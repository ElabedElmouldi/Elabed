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

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v560.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

INITIAL_BALANCE = 1000.0    
TRADE_AMOUNT_USD = 50.0     
MAX_VIRTUAL_TRADES = 20     
STOP_LOSS_PCT = 0.02        
TAKE_PROFIT_PCT = 0.03      

MAX_SCAN_LIST = 600
CHUNK_SIZE = 150
current_chunk_index = 0
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

# --- 3. محرك التحليل (نظام النقاط الخمس) ---
def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, TF_FAST, limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        # حساب المؤشرات السريعة
        df['ema'] = df['c'].ewm(span=10).mean()
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/(loss + 1e-9))))
        
        score = 0
        curr = df['c'].iloc[-1]
        
        # الاستراتيجيات الخمس (القوائم)
        if curr > df['ema'].iloc[-1]: score += 1 # 1. قائمة الاتجاه
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1 # 2. قائمة السيولة
        if 45 <= rsi.iloc[-1] <= 75: score += 1 # 3. قائمة الزخم (RSI)
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.4: score += 1 # 4. قائمة القفزة السعرية
        if curr > df['h'].tail(5).max() * 0.995: score += 1 # 5. قائمة الاختراق القريب

        return {'symbol': symbol, 'price': curr, 'score': score}
    except: return None

# --- 4. رادار المسح المطور ---
def radar_engine():
    global current_chunk_index, virtual_balance
    send_telegram("📡 *تم تشغيل نظام القوائم الثلاث v5.6.0*")
    
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

            # 1. استخراج أفضل 10 عملات في المسح (حسب الـ Score)
            top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]
            
            top_msg = f"🏆 *أفضل 10 عملات في المسح ({current_chunk_index+1}/4)*\n"
            for i, res in enumerate(top_10):
                top_msg += f"{i+1}. `{res['symbol']}` | النقاط: `{res['score']}/5`\n"
            send_telegram(top_msg)

            # 2. فلترة العملات التي حققت 3 قوائم على الأقل للدخول
            qualified_entries = [r for r in results if r['score'] >= 3]
            
            entry_summary = "📝 *عملات حققت شرط الدخول (3+ قوائم):*\n"
            if not qualified_entries: entry_summary += "_لا توجد عملات مطابقة حالياً_"
            else:
                for res in qualified_entries:
                    entry_summary += f"• `{res['symbol']}` ({res['score']} قوائم)\n"
                    
                    # تنفيذ الدخول الفعلي
                    if res['symbol'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                        if virtual_balance >= TRADE_AMOUNT_USD:
                            now = datetime.now()
                            virtual_trades[res['symbol']] = {
                                'entry': res['price'],
                                'start_full_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                                'score_at_entry': res['score']
                            }
                            virtual_balance -= TRADE_AMOUNT_USD
                            save_data()
                            send_telegram(f"🚀 *دخول صفقة:* `{res['symbol']}`\n💰 السعر: `{res['price']}`\n📊 القوائم المحققة: `{res['score']}`")

            send_telegram(entry_summary)
            send_telegram(f"✅ *تم مسح 150 عملة بنجاح*")

            current_chunk_index += 1
            time.sleep(20)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(20)

# --- 5. مراقبة الصفقات (البيع) ---
def monitor_trades():
    global virtual_balance
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                gain = (cp - trade['entry']) / trade['entry']
                
                exit_now = False
                if gain >= TAKE_PROFIT_PCT or gain <= -STOP_LOSS_PCT:
                    exit_now = True

                if exit_now:
                    virtual_balance += (TRADE_AMOUNT_USD * (1 + gain))
                    send_telegram(f"🏁 *إغلاق:* `{s}` | النتيجة: `{gain*100:+.2f}%` \n💰 الرصيد: `{virtual_balance:.2f}$`")
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except: time.sleep(5)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Bot Running"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    radar_engine()
