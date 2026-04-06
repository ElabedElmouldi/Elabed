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

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

# إعدادات الاستراتيجية
MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03 
TRAILING_GAP = 0.01      
STOP_LOSS_PCT = 0.035    
MIN_DISTANCE_FROM_RES = 0.02 # يجب أن يكون السعر بعيداً عن المقاومة بنسبة 2% على الأقل

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. دوال التحليل الفني اليدوية ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def get_resistance_level(symbol):
    """تحديد أقرب مستوى مقاومة قوي (أعلى سعر في آخر 100 شمعة ساعة)"""
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
        current_price = df['c'].iloc[-1]
        
        # 1. RSI (5 نقاط)
        df['rsi'] = calculate_rsi(df['c'])
        rsi = df['rsi'].iloc[-1]
        if 50 < rsi < 65: score += 5 
        elif 65 <= rsi < 75: score += 3 
        
        # 2. EMA (5 نقاط)
        df['ema20'] = calculate_ema(df['c'], 20)
        df['ema50'] = calculate_ema(df['c'], 50)
        if current_price > df['ema20'].iloc[-1] > df['ema50'].iloc[-1]: score += 5
            
        # 3. السيولة (5 نقاط)
        avg_vol = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_vol * 2.0: score += 5
        elif df['v'].iloc[-1] > avg_vol * 1.3: score += 3 
            
        # 4. الزخم السعري (5 نقاط)
        chg = ((current_price - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 2.0 < chg < 5.0: score += 5
        elif 0.5 < chg <= 2.0: score += 2
            
        return score, current_price, chg
    except: return 0, 0, 0

# --- 3. المحرك الرئيسي (مع فلتر المقاومات) ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🛡️ *رادار النخبة v34.0 مفعّل*\nنظام السكور الكامل + فلتر المقاومات القوية.")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            markets = exchange.fetch_markets()
            all_usdt_pairs = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot']]
            tickers = exchange.fetch_tickers(all_usdt_pairs)
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    if tickers.get(s, {}).get('quoteVolume', 0) > 1500000:
                        score, price, chg = calculate_total_score(s)
                        if score >= 10:
                            return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                return None

            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(process_scan, all_usdt_pairs))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            if top_10:
                best = top_10[0]
                s, score, price = best['symbol'], best['score'], best['price']
                
                # التحقق من المقاومة قبل أي قرار
                resistance = get_resistance_level(s)
                dist_to_res = (resistance - price) / price if resistance > price else 1.0 # 1.0 تعني اخترق المقاومة (سماء مفتوحة)
                
                is_safe_path = dist_to_res >= MIN_DISTANCE_FROM_RES or price > resistance

                should_enter = False
                entry_reason = ""

                if is_safe_path:
                    # 1. دخول فوري (20/20)
                    if score >= 20:
                        should_enter = True
                        entry_reason = "🔥 انفجار فوري (20/20) + طريق مفتوح"
                    # 2. تأكيد صدارة
                    else:
                        if s == leaderboard_tracker["symbol"]:
                            leaderboard_tracker["count"] += 1
                        else:
                            leaderboard_tracker["symbol"] = s
                            leaderboard_tracker["count"] = 1
                        
                        if leaderboard_tracker["count"] >= 3 and score >= 14:
                            should_enter = True
                            entry_reason = f"🏆 صدارة مستقرة ({leaderboard_tracker['count']}/3)"

                if should_enter and len(active_trades) < MAX_TRADES:
                    active_trades[s] = {'entry': price, 'highest_price': price, 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                    send_telegram(f"🚀 *فتح صفقة ذكية:*\n🪙 العملة: `{s}`\n📝 السبب: {entry_reason}\n🎯 الهدف القادم: `{resistance}`")
                    leaderboard_tracker = {"symbol": None, "count": 0}

            # التقرير الدوري
            report = f"📋 *رادار النخبة الدوري*\n⏰ `{now.strftime('%H:%M:%S')}`\n━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | سكور: *{c['score']}/20* | `{c['change']:+.2f}%` \n"
            send_telegram(report)

            time.sleep(600)
        except: time.sleep(30)

# --- (بقية الدوال monitor_trades و Flask تبقى كما هي) ---

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; trade = active_trades[s]
                if cp > trade.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                gain = (cp - trade['entry']) / trade['entry']
                drop = (trade['highest_price'] - cp) / trade['highest_price']
                if gain >= ACTIVATION_PROFIT and not trade.get('trailing_notified', False):
                    send_telegram(f"🎯 *تأمين:* `{s}` (+{gain*100:.2f}%) 🛡️"); active_trades[s]['trailing_notified'] = True
                exit_now = False
                if gain <= -STOP_LOSS_PCT: exit_now = True; res = "🛑 وقف خسارة"
                elif trade.get('trailing_notified') and drop >= TRAILING_GAP: exit_now = True; res = "💰 جني أرباح"
                if exit_now:
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    send_telegram(f"🏁 *إغلاق:* `{s}` | `{gain*100:+.2f}%` \n💰 المحفظة: `${bal:.2f}`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1); del active_trades[s]
            time.sleep(15)
        except: time.sleep(10)

app = Flask(__name__)
@app.route('/')
def home(): return "Safe Sniper Online"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
