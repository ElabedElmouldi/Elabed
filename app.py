import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask, request
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات والروابط ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
WEB_URL = "https://your-app-name.onrender.com" 

# الإعدادات المالية (السكالبينج السريع)
MAX_TRADES = 10
TRADE_VALUE_USD = 100
ACTIVATION_PROFIT = 0.03  # 3%
TRAILING_GAP = 0.01       # 1%
STOP_LOSS_PCT = 0.035     # 3.5%

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
START_TIME = datetime.now()

# --- 2. وظائف التلجرام والتحليل ---

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def analyze_v20_fast(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=30)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        last_change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if last_change > 7.0: return 0
        
        score = 0
        if df['v'].iloc[-1] > df['v'].iloc[-10:-1].mean() * 2.5: score += 10
        if df['c'].iloc[-1] > df['c'].ewm(span=20).mean().iloc[-1]: score += 10
        return score
    except: return 0

# --- 3. المحرك الرئيسي (المسح + الإرسال التلقائي للأوائل) ---

def main_engine():
    global blacklist_coins
    send_telegram("🚀 *Sniper v22.0 Activated*\n📊 سأرسل قائمة أفضل 10 عملات تلقائياً بعد كل مسح.")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}

            # جلب البيانات الأساسية للمسح
            tickers = exchange.fetch_tickers()
            targets = sorted([s for s in tickers.keys() if '/USDT' in s], 
                            key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
            
            candidates = []

            # فحص متوازي لـ 900 عملة
            def check_logic(s):
                score = analyze_v20_fast(s)
                if score >= 10: # نقبل من 10 نقاط لعرضها في القائمة
                    return {'symbol': s, 'score': score, 'price': tickers[s]['last'], 'change': tickers[s]['percentage']}
                return None

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(check_logic, targets))
                candidates = [r for r in results if r]

            if candidates:
                # ترتيب المرشحين حسب النقاط ثم الصعود الأقوى
                candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
                top_10 = candidates[:10]

                # 📝 بناء رسالة قائمة أفضل 10 (تُرسل تلقائياً)
                list_msg = f"📋 *قائمة النخبة (أفضل 10 عملات الآن)*\n"
                list_msg += f"⏰ الوقت: `{now.strftime('%H:%M:%S')}`\n"
                list_msg += "━━━━━━━━━━━━━━\n"
                for i, c in enumerate(top_10, 1):
                    emoji = "🔥" if i <= 3 else "✅"
                    list_msg += f"{emoji} `{c['symbol']}` | النقاط: `{c['score']}/20` | `{c['change']:+.2f}%` \n"
                list_msg += "━━━━━━━━━━━━━━\n"
                list_msg += "_سيتم الدخول تلقائياً في المركز الأول إذا توفرت السيولة._"
                
                send_telegram(list_msg)

                # 🎯 تنفيذ الدخول الفعلي في "المركز الأول" فقط
                best = top_10[0]
                if len(active_trades) < MAX_TRADES and best['symbol'] not in active_trades and best['symbol'] not in blacklist_coins and best['score'] >= 15:
                    s, p = best['symbol'], best['price']
                    active_trades[s] = {'entry': p, 'highest_price': p, 'time': now.strftime('%H:%M:%S')}
                    
                    sl = p * (1 - STOP_LOSS_PCT)
                    tp = p * (1 + ACTIVATION_PROFIT)
                    
                    entry_msg = (
                        f"🔔 *دخول صفقة (المركز الأول)*\n"
                        f"🪙 العملة: `{s}`\n💰 السعر: `{p}`\n🛑 الوقف: `{sl:.8f}` | 🎯 الهدف: `{tp:.8f}`"
                    )
                    send_telegram(entry_msg)

            time.sleep(600) # مسح شامل وإرسال تقرير كل 10 دقائق
        except: time.sleep(10)

# --- 4. بقية الكود (Monitor & Flask) ---
# (نفس وظائف monitor_trades و keep_alive السابقة)

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; trade = active_trades[s]
                if cp > trade['highest_price']: active_trades[s]['highest_price'] = cp
                gain = (cp - trade['entry']) / trade['entry']
                drop = (trade['highest_price'] - cp) / trade['highest_price']
                if gain <= -STOP_LOSS_PCT or (gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP):
                    pnl = gain * 100
                    send_telegram(f"🏁 *إغلاق:* `{s}` الربح: `{pnl:+.2f}%`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1)
                    del active_trades[s]
            time.sleep(10)
        except: time.sleep(5)

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
