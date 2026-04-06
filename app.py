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

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الحسابات التقنية اليدوية ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calculate_total_score(symbol):
    try:
        # جلب البيانات لفريم 15 دقيقة
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        score = 0
        
        # 1. نقاط RSI (حتى 5 نقاط)
        df['rsi'] = calculate_rsi(df['c'])
        rsi = df['rsi'].iloc[-1]
        if 50 < rsi < 68: score += 5 
        elif 68 <= rsi < 78: score += 2 
        
        # 2. نقاط المتوسطات EMA (حتى 5 نقاط)
        df['ema20'] = calculate_ema(df['c'], 20)
        df['ema50'] = calculate_ema(df['c'], 50)
        if df['c'].iloc[-1] > df['ema20'].iloc[-1] > df['ema50'].iloc[-1]: score += 5
            
        # 3. نقاط انفجار السيولة (حتى 5 نقاط)
        avg_vol = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_vol * 1.8: score += 5
            
        # 4. نقاط التغير السعري (حتى 5 نقاط)
        chg = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 1.5 < chg < 5.0: score += 5
            
        return score, df['c'].iloc[-1], chg
    except: return 0, 0, 0

# --- 3. المحرك الرئيسي (مسح كامل أزواج USDT) ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🔍 *رادار بايننس الشامل v32.0*\nجاري فحص جميع أزواج USDT المتاحة...")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            # --- التعديل الجوهري: جلب كل العملات المتاحة مقابل USDT ---
            markets = exchange.fetch_markets()
            all_usdt_pairs = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot']]
            
            # جلب بيانات الـ Tickers لفلترة السيولة الضعيفة قبل التحليل العميق
            tickers = exchange.fetch_tickers(all_usdt_pairs)
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    ticker = tickers.get(s, {})
                    # فلترة: حجم التداول > مليون دولار للتأكد من وجود سيولة حقيقية
                    if ticker.get('quoteVolume', 0) > 1000000:
                        score, price, chg = calculate_total_score(s)
                        if score >= 8: # عرض العملات التي تبدي أي إيجابية
                            return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                return None

            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(process_scan, all_usdt_pairs))
                candidates = [r for r in results if r]

            # ترتيب حسب السكور الأعلى
            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # منطق الصدارة الثلاثي
            if top_10:
                best_now = top_10[0]['symbol']
                if best_now == leaderboard_tracker["symbol"]:
                    leaderboard_tracker["count"] += 1
                else:
                    leaderboard_tracker["symbol"] = best_now
                    leaderboard_tracker["count"] = 1

            # إرسال التقرير
            report = f"📋 *تقرير نخبة بايننس (أزواج USDT)*\n⏰ `{now.strftime('%H:%M:%S')}`\n"
            report += f"📑 تم فحص: `{len(all_usdt_pairs)}` زوجاً\n"
            report += "━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | سكور: *{c['score']}/20* | `{c['change']:+.2f}%` \n"
            report += "━━━━━━━━━━━━━━\n"
            report += f"🏆 المتصدر: `{leaderboard_tracker['symbol']}` ({leaderboard_tracker['count']}/3)"
            send_telegram(report)

            # تنفيذ الدخول
            if leaderboard_tracker["count"] >= 3 and len(active_trades) < MAX_TRADES:
                best = top_10[0]
                if best['score'] >= 14: # دخول عند سكور قوي فقط
                    s, p = best['symbol'], best['price']
                    active_trades[s] = {'entry': p, 'highest_price': p, 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                    send_telegram(f"🚀 *دخول استراتيجي:* `{s}` بسكور `{best['score']}`.")
                    leaderboard_tracker = {"symbol": None, "count": 0}

            time.sleep(600)
        except Exception as e:
            time.sleep(30)

# --- 4. مراقبة الصفقات و Flask ---

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
                if gain <= -STOP_LOSS_PCT: exit_now = True; res = "🛑 SL"
                elif trade.get('trailing_notified') and drop >= TRAILING_GAP: exit_now = True; res = "💰 TP"
                if exit_now:
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    send_telegram(f"🏁 *إغلاق:* `{s}` | النتيجة: `{gain*100:+.2f}%` \n💰 الرصيد: `${bal:.2f}`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1); del active_trades[s]
            time.sleep(15)
        except: time.sleep(10)

app = Flask(__name__)
@app.route('/')
def home(): return "Scanner Online"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
