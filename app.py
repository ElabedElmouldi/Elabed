import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات وإدارة المخاطر ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({
    'apiKey': os.environ.get('BINANCE_API_KEY', ''),
    'secret': os.environ.get('BINANCE_SECRET', ''),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# ثوابت المحفظة والتتبع
TRADE_AMOUNT_USD = 100.0   
MAX_TRADES = 10            
ACTIVATION_PROFIT = 0.03   # تفعيل التتبع عند 3%
TRAILING_GAP = 0.015       # فارق التتبع 1.5%
STOP_LOSS_PCT = 0.035      # وقف خسارة 3.5%
MONITOR_INTERVAL = 10      # فحص كل 10 ثوانٍ

active_trades = {}    
blacklist_coins = {} 
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك الـ 20 شرطاً لحساب السكور (Advanced Score 20/20) ---
def calculate_20_point_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        score = 0
        
        # مؤشرات مساعدة
        ema20 = df['c'].ewm(span=20).mean(); ema50 = df['c'].ewm(span=50).mean()
        # RSI
        delta = df['c'].diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
        # MACD
        exp1 = df['c'].ewm(span=12).mean(); exp2 = df['c'].ewm(span=26).mean(); macd = exp1 - exp2; sig = macd.ewm(span=9).mean()
        
        # الفئات (20 شرط):
        # الاتجاه (5)
        if cp > ema20.iloc[-1]: score += 1
        if ema20.iloc[-1] > ema50.iloc[-1]: score += 1
        if cp > df['c'].rolling(100).mean().iloc[-1]: score += 1
        if cp > df['o'].iloc[-1]: score += 1
        if df['l'].iloc[-1] > df['l'].iloc[-2]: score += 1
        
        # الزخم (5)
        if 50 < rsi < 75: score += 1
        if rsi > 60: score += 1
        if macd.iloc[-1] > sig.iloc[-1]: score += 1
        if macd.iloc[-1] > 0: score += 1
        if cp > df['h'].tail(5).mean(): score += 1
        
        # السيولة (5)
        avg_v = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_v: score += 1
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 1
        if df['v'].iloc[-1] > avg_v * 1.5: score += 1
        if df['v'].tail(5).mean() > avg_v: score += 1
        if (df['c'].iloc[-1] - df['o'].iloc[-1]) > 0 and df['v'].iloc[-1] > avg_v: score += 1
        
        # حركة السعر (5)
        chg_1h = ((cp - df['c'].iloc[-4]) / df['c'].iloc[-4]) * 100
        if 0.5 < chg_1h < 4: score += 1
        if cp == df['h'].iloc[-1]: score += 1
        if (df['h'].iloc[-1] - df['l'].iloc[-1]) > (df['h'].iloc[-2] - df['l'].iloc[-2]): score += 1
        if (cp - df['l'].iloc[-1]) > (df['h'].iloc[-1] - cp): score += 1
        if cp > df['c'].rolling(10).max().iloc[-2]: score += 1 # اختراق قمة قريبة
        
        return score, cp, ((cp - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
    except: return 0, 0, 0

# --- 3. مراقبة الصفقات (تتبع 1.5% وتحديث 10ث) ---
def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; tr = active_trades[s]
                if cp > tr.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                
                gain = (cp - tr['entry']) / tr['entry']
                drop = (tr['highest_price'] - cp) / tr['highest_price']
                
                if gain >= ACTIVATION_PROFIT and not tr.get('trailing_active', False):
                    active_trades[s]['trailing_active'] = True
                    send_telegram(f"🎯 *تأمين:* `{s}` (+3%)\n🛡️ تفعيل التتبع بفارق 1.5%.")

                if tr.get('trailing_active'):
                    if drop >= TRAILING_GAP:
                        send_telegram(f"🏁 *جني أرباح:* `{s}` | `{gain*100:+.2f}%` ")
                        close_trade(s)
                else:
                    if gain <= -STOP_LOSS_PCT:
                        send_telegram(f"🛑 *وقف خسارة:* `{s}` | `{gain*100:+.2f}%` ")
                        close_trade(s)
            time.sleep(MONITOR_INTERVAL)
        except: time.sleep(5)

def close_trade(symbol):
    if symbol in active_trades:
        blacklist_coins[symbol] = datetime.now() + timedelta(hours=1)
        del active_trades[symbol]

# --- 4. المحرك الرئيسي (مسح 500 عملة) ---
def main_engine():
    send_telegram(f"🚀 *انطلاق القناص v50.0*\n🔍 مسح 500 عملة | 📈 نظام 20 شرطاً\n💰 دخول بـ ${TRADE_AMOUNT_USD}")
    
    while True:
        try:
            send_telegram("🔍 *بدء مسح الـ 500 عملة الآن...*")
            now = datetime.now()
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
            
            tickers = exchange.fetch_tickers(all_usdt)
            sorted_v = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0) if x in tickers else 0, reverse=True)
            target_list = sorted_v[20:520] 
            
            candidates = []
            with ThreadPoolExecutor(max_workers=10) as exec:
                def scan(s):
                    if s not in active_trades and s not in blacklist_coins:
                        sc, pr, ch = calculate_20_point_score(s)
                        if sc >= 12: return {'symbol': s, 'score': sc, 'price': pr, 'change': ch}
                    return None
                results = list(exec.map(scan, target_list))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: x['score'], reverse=True)
            top_10 = candidates[:10]

            report = f"🔝 *أفضل 10 ترشيحات (السكور من 20):*\n━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                m = "🥇" if i == 1 else "🔹"
                report += f"{m} `{c['symbol']}` | سكور: `{c['score']}/20` | `{c['change']:+.2f}%` \n"
            send_telegram(report)

            if top_10 and len(active_trades) < MAX_TRADES:
                best = top_10[0]
                if best['score'] >= 15: # الدخول إذا حقق 15 شرطاً من أصل 20
                    balance = exchange.fetch_balance()
                    if balance['free'].get('USDT', 0) >= TRADE_AMOUNT_USD:
                        symbol = best['symbol']
                        active_trades[symbol] = {
                            'entry': best['price'], 'highest_price': best['price'],
                            'time': now.strftime('%H:%M:%S'), 'trailing_active': False
                        }
                        entry_msg = f"✅ *فتح صفقة:* `{symbol}`\n💰 السعر: `{best['price']}`\n🛑 وقف الخسارة: `{best['price']*(1-STOP_LOSS_PCT):.4f}`\n⏱️ الوقت: `{now.strftime('%H:%M:%S')}`\n💼 صفقات: `{len(active_trades)}/10`"
                        send_telegram(entry_msg)

            time.sleep(300)
        except Exception as e:
            send_telegram(f"⚠️ خطأ: {str(e)}")
            time.sleep(30)

app = Flask(__name__)
@app.route('/')
def home(): return "Mouldi Sniper v50.0 - Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port, use_reloader=False)).start()
    Thread(target=monitor_trades).start()
    main_engine()
