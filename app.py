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

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "gold_pentagram_v450.json"
exchange = ccxt.binance({'enableRateLimit': True})

SCAN_INTERVAL = 900 
DAILY_GOAL_PCT = 3.0
MAX_VIRTUAL_TRADES = 5
STABLE_COINS = ['USDT', 'FDUSD', 'USDC', 'BUSD', 'DAI', 'EUR', 'GBP']

# --- 2. محرك الاستراتيجيات الخمس ---

def get_scores(symbol):
    try:
        # جلب البيانات لفريمات مختلفة
        df_15m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '15m', 100), columns=['t','o','h','l','c','v'])
        df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', 50), columns=['t','o','h','l','c','v'])
        cp = df_15m['c'].iloc[-1]
        
        # 1. سكور السيولة (Momentum)
        rvol = df_15m['v'].iloc[-1] / df_15m['v'].tail(20).mean()
        s1 = round(rvol * 5, 2)
        
        # 2. سكور الاختراق (Breakout)
        high_24h = df_15m['h'].tail(96).max()
        s2 = round(20 if cp >= high_24h else (cp/high_24h)*10, 2)
        
        # 3. سكور الاتجاه (Trend - Multi-TF)
        ema20_15 = df_15m['c'].ewm(span=20).mean().iloc[-1]
        ema20_1h = df_1h['c'].ewm(span=20).mean().iloc[-1]
        s3 = 10 if (cp > ema20_15 and cp > ema20_1h) else 0
        
        # 4. سكور القوة النسبية (Relative Strength)
        change_15m = ((cp - df_15m['o'].iloc[-1]) / df_15m['o'].iloc[-1]) * 100
        s4 = round(change_15m * 4, 2)
        
        # 5. سكور الضغط (Squeeze/Volatility)
        std = df_15m['c'].tail(20).std()
        sma = df_15m['c'].tail(20).mean()
        bw = (std * 4) / sma # Bandwidth
        s5 = round((1/bw) * 2, 2) # كلما ضاق النطاق زاد السكور
        
        return {'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 'price': cp}
    except: return None

# --- 3. إدارة الصفقات والبيانات ---

virtual_trades = {}
virtual_balance = 1000.0
daily_pnl = 0.0

def load_data():
    global virtual_balance, virtual_trades, daily_pnl
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', 1000.0)
                virtual_trades = data.get('virtual_trades', {})
                daily_pnl = data.get('daily_pnl', 0.0)
        except: pass

def save_data():
    try:
        data = {'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades, 'daily_pnl': daily_pnl}
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 4. المحرك الرئيسي ---

def monitor_trades():
    global virtual_balance, daily_pnl
    while True:
        try:
            for s in list(virtual_trades.keys()):
                t = virtual_trades[s]
                cp = exchange.fetch_ticker(s)['last']
                gain = (cp - t['entry']) / t['entry']
                
                # وقت الصفقة
                start = datetime.strptime(t['start'], '%Y-%m-%d %H:%M:%S')
                duration = str(datetime.now() - start).split('.')[0]

                exit_now = False
                if gain <= -0.015: exit_now = True # SL 1.5%
                elif gain >= 0.03: exit_now = True # TP 3.0%

                if exit_now:
                    pnl = 100 * gain
                    virtual_balance += pnl; daily_pnl += pnl
                    msg = f"🏁 *نهاية الصفقة*\n🪙 العملة: `{s}`\n📈 النتيجة: `{gain*100:+.2f}%`\n⏱️ المدة: `{duration}`\n📊 أداء اليوم: `{(daily_pnl/virtual_balance)*100:.2f}%`"
                    send_telegram(msg)
                    del virtual_trades[s]; save_data()
            time.sleep(20)
        except: time.sleep(10)

def radar_engine():
    send_telegram("🔱 *تم تفعيل نظام الخماسية الذهبية v450*\nتحليل 5 استراتيجيات لفلترة الانفجار...")
    while True:
        try:
            tickers = exchange.fetch_tickers()
            all_usdt = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]
            targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:120]

            with ThreadPoolExecutor(max_workers=15) as exec:
                results = list(filter(None, exec.map(get_scores, targets)))

            # استخراج أفضل 10 لكل قائمة
            L1 = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            L2 = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            L3 = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]
            L4 = sorted(results, key=lambda x: x['s4'], reverse=True)[:10]
            L5 = sorted(results, key=lambda x: x['s5'], reverse=True)[:10]

            # البحث عن العملات المشتركة في القوائم الخمس
            sets = [ {r['symbol'] for r in L} for L in [L1, L2, L3, L4, L5] ]
            common = set.intersection(*sets)

            # تقرير القوائم
            report = "📊 *القوائم الخمس (أفضل 10):*\n"
            report += "1️⃣ *السيولة:* " + ", ".join([r['symbol'].split('/')[0] for r in L1]) + "\n"
            report += "2️⃣ *الاختراق:* " + ", ".join([r['symbol'].split('/')[0] for r in L2]) + "\n"
            report += "3️⃣ *الاتجاه:* " + ", ".join([r['symbol'].split('/')[0] for r in L3]) + "\n"
            report += "4️⃣ *القوة:* " + ", ".join([r['symbol'].split('/')[0] for r in L4]) + "\n"
            report += "5️⃣ *الضغط:* " + ", ".join([r['symbol'].split('/')[0] for r in L5])
            send_telegram(report)

            if common:
                # اختيار الأعلى سكور إجمالي من المشتركين
                finalists = []
                for sym in common:
                    d = next(r for r in results if r['symbol'] == sym)
                    total = d['s1'] + d['s2'] + d['s3'] + d['s4'] + d['s5']
                    finalists.append({'s': sym, 'total': total, 'p': d['price']})
                
                best = sorted(finalists, key=lambda x: x['total'], reverse=True)[0]
                
                if best['s'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                    virtual_trades[best['s']] = {'entry': best['p'], 'start': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    save_data()
                    send_telegram(f"🔥 *فرصة ذهبية نادرة (إجماع 5/5)*\n🪙 العملة: `{best['s']}`\n💰 السعر: `{best['p']}`\n📊 السكور الكلي: `{best['total']:.2f}`")
            
            time.sleep(SCAN_INTERVAL)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(30)

# --- 5. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Pentagram System Active"

if __name__ == "__main__":
    load_data()
    Thread(target=monitor_trades, daemon=True).start()
    Thread(target=radar_engine, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
