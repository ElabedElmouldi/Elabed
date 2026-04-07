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

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
DATA_FILE = "gold_trader_v591.json"

exchange = ccxt.binance({'enableRateLimit': True})
TF_FAST = '1m'

INITIAL_BALANCE = 1000.0    
TRADE_AMOUNT_USD = 50.0     
MAX_VIRTUAL_TRADES = 20     
STOP_LOSS_PCT = 0.02        
TAKE_PROFIT_PCT = 0.03      

MAX_SCAN_LIST = 600
CHUNK_SIZE = 150
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
        except Exception as e:
            print(f"Load Error: {e}")

def save_data():
    try:
        data = {'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades}
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Save Error: {e}")

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except:
            pass

# --- 3. محرك التحليل ---
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
        
        if curr > df['ema'].iloc[-1]: score += 1                
        if df['v'].iloc[-1] > (df['v'].tail(10).mean() * 2.5): score += 1 
        if 50 <= rsi.iloc[-1] <= 75: score += 1                 
        if ((curr - df['c'].iloc[-2])/df['c'].iloc[-2])*100 >= 0.45: score += 1 
        if curr > df['h'].tail(5).max() * 0.997: score += 1     

        return {'symbol': symbol, 'price': curr, 'score': score}
    except:
        return None

# --- 4. رادار المسح الدوري (كل 15 دقيقة) ---
def radar_engine():
    global virtual_balance
    send_telegram(f"🕒 *بدء نظام المسح الشامل v5.9.1*\nإعادة المسح كل {SCAN_INTERVAL_MINUTES} دقيقة.")
    
    while True:
        cycle_start = datetime.now()
        try:
            tickers = exchange.fetch_tickers()
            all_targets = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_AND_GIANTS]
            sorted_targets = sorted(all_targets, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:MAX_SCAN_LIST]
            
            chunks = [sorted_targets[i:i + CHUNK_SIZE] for i in range(0, len(sorted_targets), CHUNK_SIZE)]
            all_results = []
            
            for chunk in chunks:
                with ThreadPoolExecutor(max_workers=15) as executor:
                    batch_results = list(filter(None, executor.map(analyze_coin, chunk)))
                    all_results.extend(batch_results)
                time.sleep(1)

            list_5 = [r for r in all_results if r['score'] == 5]
            list_4 = [r for r in all_results if r['score'] == 4]

            if list_5 or list_4:
                msg = "💎 *نتائج النخبة المكتشفة*\n"
                if list_5: msg += f"🔥 *5 قوائم:* `{', '.join([r['symbol'] for r in list_5])}`\n"
                if list_4: msg += f"⚡ *4 قوائم:* `{', '.join([r['symbol'] for r in list_4])}`\n"
                send_telegram(msg)

                for res in (list_5 + list_4):
                    if res['symbol'] not in virtual_trades:
                        if len(virtual_trades) < MAX_VIRTUAL_TRADES and virtual_balance >= TRADE_AMOUNT_USD:
                            virtual_trades[res['symbol']] = {
                                'entry': res['price'],
                                'start_full_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                            virtual_balance -= TRADE_AMOUNT_USD
                            save_data()
                            send_telegram(f"🚀 *دخول صفقة:* `{res['symbol']}`")

            send_telegram(f"✅ تم انتهاء الدورة. القادمة: {(cycle_start + timedelta(minutes=SCAN_INTERVAL_MINUTES)).strftime('%H:%M')}")

        except Exception as e:
            print(f"Radar Error: {e}")
            time.sleep(10)
        
        # انتظار حتى موعد الدورة القادمة
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
                    res_text = "✅ ربح" if gain > 0 else "❌ خسارة"
                    send_telegram(f"🏁 *إغلاق صفقة:* `{s}`\n📊 النتيجة: `{gain*100:+.2f}%` ({res_text})\n💰 الرصيد المتاح: `{virtual_balance:.2f}$`")
                    del virtual_trades[s]
                    save_data()
            time.sleep(10)
        except Exception as e:
            print(f"Monitor Error: {e}")
            time.sleep(5)

# --- 6. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Bot Running"

if __name__ == "__main__":
    load_data()
    # تشغيل Flask في الخلفية
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    # تشغيل مراقب الصفقات في الخلفية
    Thread(target=monitor_trades).start()
    # تشغيل الرادار في المسار الرئيسي
    radar_engine()
