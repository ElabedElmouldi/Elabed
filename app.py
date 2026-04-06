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

# --- 2. ميزة تقرير الصفقات المفتوحة (كل 10 دقائق) ---
def open_trades_report():
    """وظيفة ترسل حالة الصفقات المفتوحة فقط كل 10 دقائق"""
    while True:
        try:
            if active_trades:
                report = "🔔 *تقرير الصفقات المفتوحة الآن:*\n"
                report += "━━━━━━━━━━━━━━\n"
                for s, data in active_trades.items():
                    ticker = exchange.fetch_ticker(s)
                    current_price = ticker['last']
                    gain = (current_price - data['entry']) / data['entry'] * 100
                    status = "✅ رابحة" if gain > 0 else "🔻 خاسرة"
                    report += f"🪙 `{s}`\n💰 الربح: `{gain:+.2f}%` ({status})\n⏱️ منذ: `{data['time']}`\n"
                    report += "──────\n"
                send_telegram(report)
            else:
                # اختياري: إرسال رسالة تفيد بعدم وجود صفقات حالياً
                send_telegram("ℹ️ *تقرير:* لا توجد صفقات مفتوحة حالياً.")
            
            time.sleep(600) # الانتظار 10 دقائق (600 ثانية)
        except Exception as e:
            time.sleep(60)

# --- 3. محرك التحليل الفني ---
def calculate_total_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        score = 0
        cp = df['c'].iloc[-1]
        
        # RSI
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        if 50 < rsi < 70: score += 5
        
        # EMA
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        ema50 = df['c'].ewm(span=50).mean().iloc[-1]
        if cp > ema20 > ema50: score += 5
        
        # Volume & Change
        if df['v'].iloc[-1] > df['v'].tail(20).mean() * 1.8: score += 5
        chg = ((cp - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 1.5 < chg < 5.0: score += 5
        
        return score, cp, chg
    except: return 0, 0, 0

# --- 4. المحرك الرئيسي (مسح كل 5 دقائق) ---
def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🎯 *نظام النخبة v39.0 مفعّل*\n✅ تقرير المسح: كل 5 دقائق\n🔔 تقرير الصفقات: كل 10 دقائق")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
            tickers = exchange.fetch_tickers(all_usdt)
            sorted_all = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0) if x in tickers else 0, reverse=True)
            target_list = sorted_all[20:320] 
            
            candidates = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                def scan(s):
                    if s not in active_trades and s not in blacklist_coins:
                        score, price, chg = calculate_total_score(s)
                        if score >= 10: return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                    return None
                results = list(executor.map(scan, target_list))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # تقرير المسح العام (كل 5 دقائق)
            report = f"📋 *رادار المسح (300 عملة)*\n⏰ `{now.strftime('%H:%M:%S')}`\n"
            if not top_10: report += "⚠️ لا توجد فرص جديدة."
            else:
                for i, c in enumerate(top_10, 1):
                    report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | `{c['score']}/20` \n"
            send_telegram(report)

            if top_10:
                best = top_10[0]; s, score, price = best['symbol'], best['score'], best['price']
                if score >= 20 or (s == leaderboard_tracker["symbol"] and leaderboard_tracker["count"] >= 3):
                    if len(active_trades) < MAX_TRADES:
                        active_trades[s] = {'entry': price, 'highest_price': price, 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                        send_telegram(f"🚀 *فتح صفقة:* `{s}` بسكور `{score}`")
            
            time.sleep(300)
        except Exception as e:
            time.sleep(30)

# --- 5. مراقبة الصفقات اللحظية (للبيع) ---
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
def home(): return "Mouldi Bot v39"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port, use_reloader=False)).start()
    # تشغيل التقارير المزدوجة
    Thread(target=open_trades_report).start() # تقرير الصفقات كل 10 دقائق
    Thread(target=monitor_trades).start()      # مراقبة البيع اللحظي
    main_engine()                              # مسح السوق كل 5 دقائق
