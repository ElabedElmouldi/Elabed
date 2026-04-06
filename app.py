import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
RENDER_APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

# العملات المستقرة المستبعدة
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP']
MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03   
TRAILING_GAP = 0.01        
STOP_LOSS_PCT = 0.035      

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك التحليل الفني ---
def calculate_total_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        score = 0
        cp = df['c'].iloc[-1]
        
        # RSI (5 pts)
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        if 50 < rsi < 70: score += 5
        
        # EMA (5 pts)
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        ema50 = df['c'].ewm(span=50).mean().iloc[-1]
        if cp > ema20 > ema50: score += 5
        
        # Volume (5 pts)
        avg_v = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_v * 1.8: score += 5
        
        # Change (5 pts)
        chg = ((cp - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 1.5 < chg < 5.0: score += 5
        
        return score, cp, chg
    except: return 0, 0, 0

# --- 3. المحرك الرئيسي (قائمة أفضل 10 عملات) ---
def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🚀 *تم تفعيل الرادار v40.0*\n✅ سيصلك تقرير بأفضل 10 عملات كل 5 دقائق.")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
            
            tickers = exchange.fetch_tickers(all_usdt)
            # ترتيب حسب السيولة وتخطي أول 20 (الكبار)
            sorted_all = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0) if x in tickers else 0, reverse=True)
            target_list = sorted_all[20:320] 
            
            candidates = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                def scan(s):
                    if s not in active_trades and s not in blacklist_coins:
                        score, price, chg = calculate_total_score(s)
                        if score >= 6: # خفضنا الحد الأدنى للظهور في القائمة لضمان وجود 10 نتائج دائماً
                            return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                    return None
                results = list(executor.map(scan, target_list))
                candidates = [r for r in results if r]

            # ترتيب المرشحين حسب السكور ثم نسبة التغير
            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # 📝 إنشاء تقرير أفضل 10 عملات
            report = f"🔝 *أفضل 10 عملات مرشحة الآن:*\n"
            report += f"⏰ التوقيت: `{now.strftime('%H:%M:%S')}`\n"
            report += "━━━━━━━━━━━━━━\n"
            
            if not top_10:
                report += "⚠️ لا توجد عملات تحقق معايير التحليل حالياً."
            else:
                for i, c in enumerate(top_10, 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
                    report += f"{medal} *{c['symbol']}*\n"
                    report += f"   └ السكور: `{c['score']}/20` | التغير: `{c['change']:+.2f}%` \n"
            
            send_telegram(report)

            # منطق الدخول في الصفقة (للمركز الأول فقط إذا كان السكور عالياً)
            if top_10:
                best = top_10[0]
                if best['score'] >= 20 or (best['symbol'] == leaderboard_tracker["symbol"] and leaderboard_tracker["count"] >= 3):
                    if len(active_trades) < MAX_TRADES:
                        active_trades[best['symbol']] = {'entry': best['price'], 'highest_price': best['price'], 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                        send_telegram(f"🚀 *دخول تلقائي:* `{best['symbol']}`")

            time.sleep(300) # المسح القادم بعد 5 دقائق
        except Exception as e:
            time.sleep(30)

# --- الدوال المساندة (Monitor, Flask, Keep-Alive) تبقى كما هي ---
def open_trades_report():
    while True:
        try:
            if active_trades:
                rep = "🔔 *حالة الصفقات المفتوحة:*\n"
                for s, d in active_trades.items():
                    tick = exchange.fetch_ticker(s); cp = tick['last']
                    gn = (cp - d['entry']) / d['entry'] * 100
                    rep += f"🪙 `{s}`: `{gn:+.2f}%` \n"
                send_telegram(rep)
            time.sleep(600)
        except: time.sleep(60)

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; tr = active_trades[s]
                if cp > tr.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                gn = (cp - tr['entry']) / tr['entry']; dp = (tr['highest_price'] - cp) / tr['highest_price']
                if gn >= ACTIVATION_PROFIT and not tr.get('trailing_notified', False):
                    send_telegram(f"🎯 *تأمين:* `{s}` (+{gn*100:.2f}%) 🛡️"); tr['trailing_notified'] = True
                if gn <= -STOP_LOSS_PCT or (tr.get('trailing_notified') and dp >= TRAILING_GAP):
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    send_telegram(f"🏁 *إغلاق:* `{s}` | `{gn*100:+.2f}%` | `${bal:.2f}`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1); del active_trades[s]
            time.sleep(15)
        except: time.sleep(10)

app = Flask(__name__)
@app.route('/')
def home(): return "Bot v40 Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port, use_reloader=False)).start()
    Thread(target=open_trades_report).start()
    Thread(target=monitor_trades).start()
    main_engine()
