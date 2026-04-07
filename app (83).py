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

# --- 1. الإعدادات العامة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "trading_sim_v400.json"
APP_URL = "your-app-name.onrender.com" 

exchange = ccxt.binance({'enableRateLimit': True})

SCAN_INTERVAL = 900 # 15 دقيقة
DAILY_GOAL_PCT = 3.0 # الهدف اليومي الجديد
MAX_VIRTUAL_TRADES = 5
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
virtual_trades = {}
virtual_balance = 1000.0
daily_pnl_usd = 0.0
last_reset_date = str(datetime.now().date())

def load_data():
    global virtual_balance, virtual_trades, daily_pnl_usd, last_reset_date
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', 1000.0)
                virtual_trades = data.get('virtual_trades', {})
                daily_pnl_usd = data.get('daily_pnl_usd', 0.0)
                last_reset_date = data.get('last_reset_date', str(datetime.now().date()))
        except: pass

def save_data():
    try:
        data = {
            'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades,
            'daily_pnl_usd': daily_pnl_usd, 'last_reset_date': last_reset_date
        }
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. الاستراتيجيات الثلاث (حساب السكور) ---

def get_momentum_score(df):
    rvol = df['v'].iloc[-1] / df['v'].tail(20).mean()
    change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
    return round((rvol * 6) + (change * 3), 2)

def get_breakout_score(df):
    high_24h = df['h'].tail(96).max()
    cp = df['c'].iloc[-1]
    score = (cp / high_24h) * 10
    if cp >= high_24h: score += 10
    return round(score, 2)

def get_trend_score(df):
    ema20 = df['c'].ewm(span=20).mean().iloc[-1]
    cp = df['c'].iloc[-1]
    delta = df['c'].diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - (100 / (1 + (up / down))).iloc[-1]
    score = (10 if cp > ema20 else 0) + (rsi / 10)
    return round(score, 2)

# --- 4. محرك التحليل والمراقبة ---

def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        return {
            'symbol': symbol, 's1': get_momentum_score(df),
            's2': get_breakout_score(df), 's3': get_trend_score(df),
            'price': df['c'].iloc[-1]
        }
    except: return None

def monitor_trades():
    global virtual_balance, daily_pnl_usd
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s); cp = ticker['last']
                
                if cp > trade.get('highest_price', 0):
                    virtual_trades[s]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drop = (virtual_trades[s]['highest_price'] - cp) / virtual_trades[s]['highest_price']
                
                # إعدادات الخروج (تتكيف مع السوق)
                exit_now = False
                if gain <= -0.015: exit_now = True # وقف خسارة 1.5%
                elif gain >= 0.03 and drop >= 0.01: exit_now = True # ملاحقة ربح
                
                if exit_now:
                    pnl = 100 * gain
                    virtual_balance += pnl
                    daily_pnl_usd += pnl
                    daily_pct = (daily_pnl_usd / virtual_balance) * 100
                    icon = "✅" if gain > 0 else "❌"
                    send_telegram(f"{icon} *إغلاق افتراضي:* `{s}`\nالربح: `{gain*100:+.2f}%`\nأداء اليوم: `{daily_pct:.2f}% / {DAILY_GOAL_PCT}%`")
                    del virtual_trades[s]; save_data()
            time.sleep(15)
        except: time.sleep(10)

def radar_engine():
    global daily_pnl_usd, last_reset_date
    send_telegram(f"🌟 *نظام الإجماع الذهبي (v400) متصل*\nالهدف اليومي: `{DAILY_GOAL_PCT}%` | الفلترة: `Top 10`")
    
    while True:
        try:
            now = datetime.now()
            # تصفير اليومي
            if last_reset_date != str(now.date()):
                daily_pnl_usd = 0.0; last_reset_date = str(now.date()); save_data()
                send_telegram("📅 *بداية يوم جديد:* تم تصفير عداد الأرباح.")

            tickers = exchange.fetch_tickers()
            all_usdt = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]
            targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:150]

            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(filter(None, executor.map(analyze_coin, targets)))

            # استخراج أفضل 10 لكل استراتيجية
            m_list = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            b_list = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            t_list = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]

            m_set = {r['symbol'] for r in m_list}
            b_set = {r['symbol'] for r in b_list}
            t_set = {r['symbol'] for r in t_list}

            # الإجماع (العملات الموجودة في الـ 3 قوائم)
            golden_ones = m_set.intersection(b_set).intersection(t_set)

            # إرسال تقرير القوائم
            msg = "📋 *أعلى 5 عملات حالياً:*\n"
            msg += "🚀 *السيولة:* " + ", ".join([r['symbol'].replace('/USDT','') for r in m_list[:5]]) + "\n"
            msg += "📈 *الاختراق:* " + ", ".join([r['symbol'].replace('/USDT','') for r in b_list[:5]]) + "\n"
            msg += "💎 *الاتجاه:* " + ", ".join([r['symbol'].replace('/USDT','') for r in t_list[:5]])

            if golden_ones:
                msg += "\n\n🌟 *إجماع ذهبي مرصود:* " + ", ".join([f"`{s}`" for s in golden_ones])
                for sym in golden_ones:
                    if sym not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                        c_data = next(r for r in results if r['symbol'] == sym)
                        total_score = c_data['s1'] + c_data['s2'] + c_data['s3']
                        virtual_trades[sym] = {
                            'entry': c_data['price'], 'highest_price': c_data['price'],
                            'score': total_score, 'strategy': 'Golden Consensus'
                        }
                        save_data()
                        send_telegram(f"🚀 *دخول افتراضي:* `{sym}`\nالسكور الذهبي: `{total_score:.2f}`")
            
            send_telegram(msg)
            time.sleep(900)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(30)

# --- 5. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Gold System Active"

if __name__ == "__main__":
    load_data()
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_trades).start()
    radar_engine()
