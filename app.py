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
# ضع هنا رابط موقعك الذي أعطاك إياه Render (مثال: https://bot-mouldi.onrender.com)
RENDER_APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "") 

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03   
TRAILING_GAP = 0.01        
STOP_LOSS_PCT = 0.035      
MIN_DISTANCE_FROM_RES = 0.02 

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. ميزة الحفاظ على استيقاظ السيرفر (Anti-Sleep) ---
def keep_alive_ping():
    """ترسل طلباً للموقع نفسه كل 10 دقائق لمنع السيرفر من النوم"""
    while True:
        try:
            if RENDER_APP_URL:
                requests.get(RENDER_APP_URL, timeout=10)
                # لا نرسل رسالة تلجرام هنا لعدم الإزعاج، فقط نبقي السيرفر مستيقظاً
            time.sleep(600) 
        except:
            time.sleep(60)

# --- 3. الدوال التقنية ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def get_resistance_level(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        return df['h'].max()
    except: return 0

def calculate_total_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        score = 0
        curr_p = df['c'].iloc[-1]
        df['rsi'] = calculate_rsi(df['c'])
        rsi = df['rsi'].iloc[-1]
        if 50 < rsi < 65: score += 5
        elif 65 <= rsi < 75: score += 3
        df['ema20'] = calculate_ema(df['c'], 20); df['ema50'] = calculate_ema(df['c'], 50)
        if curr_p > df['ema20'].iloc[-1] > df['ema50'].iloc[-1]: score += 5
        avg_v = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_v * 1.8: score += 5
        chg = ((curr_p - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 1.5 < chg < 5.0: score += 5
        return score, curr_p, chg
    except: return 0, 0, 0

# --- 4. المحرك الرئيسي ---
def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("⚡ *بوت النخبة v37.0 مفعّل*\n🛡️ ميزة Anti-Sleep مدمجة\n⏱️ المسح: كل 5 دقائق")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot']]
            tickers = exchange.fetch_tickers(all_usdt)
            sorted_symbols = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:500]
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    if tickers[s].get('quoteVolume', 0) > 1500000:
                        score, price, chg = calculate_total_score(s)
                        if score >= 10: return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                return None

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(process_scan, sorted_symbols))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            if top_10:
                best = top_10[0]; s, score, price = best['symbol'], best['score'], best['price']
                res_level = get_resistance_level(s)
                dist = (res_level - price) / price if res_level > price else 1.0
                safe = dist >= MIN_DISTANCE_FROM_RES or price > res_level

                do_entry = False
                if safe:
                    if score >= 20: do_entry = True
                    else:
                        if s == leaderboard_tracker["symbol"]: leaderboard_tracker["count"] += 1
                        else: leaderboard_tracker["symbol"] = s; leaderboard_tracker["count"] = 1
                        if leaderboard_tracker["count"] >= 3 and score >= 14: do_entry = True

                if do_entry and len(active_trades) < MAX_TRADES:
                    active_trades[s] = {'entry': price, 'highest_price': price, 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                    send_telegram(f"✅ *دخول صفقة:* `{s}`\n🎯 المقاومة: `{res_level}`")
                    leaderboard_tracker = {"symbol": None, "count": 0}

            report = f"📋 *رادار النخبة*\n⏰ `{now.strftime('%H:%M:%S')}`\n"
            for i, c in enumerate(top_10, 1):
                report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | `{c['score']}/20` | `{c['change']:+.2f}%` \n"
            send_telegram(report)
            time.sleep(300)
        except Exception as e:
            send_telegram(f"⚠️ خطأ في المحرك: {str(e)}")
            time.sleep(30)

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; tr = active_trades[s]
                if cp > tr.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                gn = (cp - tr['entry']) / tr['entry']; dp = (tr['highest_price'] - cp) / tr['highest_price']
                if gn >= ACTIVATION_PROFIT and not tr.get('trailing_notified', False):
                    send_telegram(f"🎯 *تأمين:* `{s}` (+{gn*100:.2f}%) 🛡️"); active_trades[s]['trailing_notified'] = True
                if gn <= -STOP_LOSS_PCT or (tr.get('trailing_notified') and dp >= TRAILING_GAP):
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    send_telegram(f"🏁 *إغلاق:* `{s}` | `{gn*100:+.2f}%` | `${bal:.2f}`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1); del active_trades[s]
            time.sleep(15)
        except: time.sleep(10)

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive and Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # تشغيل Flask
    Thread(target=lambda: app.run(host='0.0.0.0', port=port, use_reloader=False)).start()
    # تشغيل ميزة منع النوم
    Thread(target=keep_alive_ping).start()
    # تشغيل المراقبة
    Thread(target=monitor_trades).start()
    # المحرك الأساسي
    main_engine()
