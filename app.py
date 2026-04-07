import ccxt
import pandas as pd
import numpy as np
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
DATA_FILE = "pro_trader_v510.json"
exchange = ccxt.binance({'enableRateLimit': True})

SCAN_INTERVAL = 900 
DAILY_GOAL_PCT = 3.0
MAX_VIRTUAL_TRADES = 5
STABLE_COINS = ['USDT', 'FDUSD', 'USDC', 'BUSD', 'DAI', 'EUR', 'GBP']

# --- 2. التحليل الفني ---
def calculate_adx(df, period=14):
    try:
        df = df.copy()
        df['h-l'] = df['h'] - df['l']
        df['h-pc'] = abs(df['h'] - df['c'].shift(1))
        df['l-pc'] = abs(df['l'] - df['c'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        df['plus_dm'] = np.where((df['h'] - df['h'].shift(1)) > (df['l'].shift(1) - df['l']), np.maximum(df['h'] - df['h'].shift(1), 0), 0)
        df['minus_dm'] = np.where((df['l'].shift(1) - df['l']) > (df['h'] - df['h'].shift(1)), np.maximum(df['l'].shift(1) - df['l'], 0), 0)
        tr_s = df['tr'].rolling(period).mean()
        p_di = 100 * (df['plus_dm'].rolling(period).mean() / tr_s)
        m_di = 100 * (df['minus_dm'].rolling(period).mean() / tr_s)
        dx = 100 * abs(p_di - m_di) / (p_di + m_di)
        return dx.rolling(period).mean().iloc[-1]
    except: return 0

def get_pro_scores(symbol, btc_change):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=50)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        v_mean = df['v'].tail(20).mean()
        
        # S1: Smart Volume
        rvol = df['v'].iloc[-1] / v_mean
        c_pos = (cp - df['l'].iloc[-1]) / (df['h'].iloc[-1] - df['l'].iloc[-1] + 1e-9)
        s1 = round(rvol * 5 * c_pos, 2)
        
        # S2: Breakout
        h_24h = df['h'].max()
        s2 = round(20 if cp >= h_24h else (cp/h_24h)*10, 2)
        
        # S3: ADX Trend
        adx = calculate_adx(df)
        ema = df['c'].ewm(span=20).mean().iloc[-1]
        s3 = 15 if (cp > ema and adx > 25) else (5 if adx > 25 else 0)
        
        # S4: Rel Strength
        c_change = ((cp - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
        s4 = round((c_change - btc_change) * 4, 2)
        
        # S5: Squeeze
        squeeze = (df['c'].tail(20).std() * 2) / df['c'].tail(20).mean()
        s5 = round((1/squeeze) * 2 if cp > ema else 0, 2)
        
        return {'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 'price': cp, 'total': s1+s2+s3+s4+s5}
    except: return None

# --- 3. الإدارة والتشغيل ---
virtual_trades = {}
virtual_balance = 1000.0
daily_pnl = 0.0

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def radar_engine():
    send_telegram("✅ *v510.0 Online*")
    while True:
        try:
            # BTC Status
            btc = exchange.fetch_ohlcv('BTC/USDT', '15m', limit=4)
            btc_change = ((btc[-1][4] - btc[0][1]) / btc[0][1]) * 100
            
            tickers = exchange.fetch_tickers()
            targets = [s for s in tickers if s.endswith('/USDT') and tickers[s].get('quoteVolume', 0) > 10000000][:100]

            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(lambda s: get_pro_scores(s, btc_change), targets)))

            # القوائم
            L1 = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            L2 = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            L3 = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]
            L4 = sorted(results, key=lambda x: x['s4'], reverse=True)[:10]
            L5 = sorted(results, key=lambda x: x['s5'], reverse=True)[:10]

            sets = [ {r['symbol'] for r in L} for L in [L1, L2, L3, L4, L5] ]
            common = set.intersection(*sets)

            report = f"📊 *الرادار الخماسي:*\n1. سيولة: {L1[0]['symbol'].split('/')[0]}\n2. اختراق: {L2[0]['symbol'].split('/')[0]}\n3. قوة: {L4[0]['symbol'].split('/')[0]}"
            send_telegram(report)

            if common:
                best = sorted([r for r in results if r['symbol'] in common], key=lambda x: x['total'], reverse=True)[0]
                send_telegram(f"🔥 *إجماع ذهبي:* `{best['symbol']}`\nسكور: `{best['total']}`")

            time.sleep(SCAN_INTERVAL)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(30)

app = Flask('')
@app.route('/')
def home(): return "Active"

if __name__ == "__main__":
    # تشغيل الرادار في الخلفية
    Thread(target=radar_engine, daemon=True).start()
    # تشغيل Flask على المنفذ الصحيح لـ Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
