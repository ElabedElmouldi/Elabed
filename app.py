import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask, request
from threading import Thread
import requests
import os
from fpdf import FPDF
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات والروابط (Render) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
WEB_URL = "https://your-app-name.onrender.com" # ضع رابط رندر هنا بعد الرفع

# الإعدادات المالية الجديدة (الاستراتيجية السريعة)
MAX_TRADES = 10
TRADE_VALUE_USD = 100
ACTIVATION_PROFIT = 0.03  # تفعيل التتبع عند 3%
TRAILING_GAP = 0.01       # فارق الملاحقة 1% (الخروج عند تراجع 1% من القمة)
STOP_LOSS_PCT = 0.035     # وقف خسارة 3.5% (لحماية الأرباح)

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
closed_today = []     
blacklist_coins = {} 
START_TIME = datetime.now()

# --- 2. نظام Flask للبقاء مستيقظاً ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"Sniper Scalper v21.0 is Live. Uptime: {str(datetime.now()-START_TIME).split('.')[0]}"

def keep_alive():
    time.sleep(60)
    while True:
        try:
            requests.get(WEB_URL, timeout=10)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat sent.")
        except: pass
        time.sleep(600)

# --- 3. وظائف التلجرام والتحليل ---

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
        
        # حماية من الـ Pump & Dump (أكثر من 7% صعود في شمعة واحدة)
        last_change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if last_change > 7.0: return 0
        
        score = 0
        # شروط النقاط الـ 20
        if df['v'].iloc[-1] > df['v'].iloc[-10:-1].mean() * 2.5: score += 10
        if df['c'].iloc[-1] > df['c'].ewm(span=20).mean().iloc[-1]: score += 10
        return score
    except: return 0

# --- 4. المحرك الرئيسي (نخبة الـ 900 عملة) ---

def main_engine():
    global blacklist_coins
    send_telegram("🚀 *Sniper v21.0 (Scalping) Deployed*\n✅ تفعيل الأرباح: `3%` | 📉 الفارق: `1%` | 🛑 الوقف: `3.5%`")
    
    while True:
        try:
            now = datetime.now()
            # تنظيف قائمة الانتظار
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}

            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                targets = sorted([s for s in tickers.keys() if '/USDT' in s], 
                                key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
                
                def check_logic(s):
                    if s not in active_trades and s not in blacklist_coins:
                        score = analyze_v20_fast(s)
                        if score >= 15:
                            return {'symbol': s, 'score': score, 'price': tickers[s]['last'], 'vol': tickers[s]['quoteVolume']}
                    return None

                with ThreadPoolExecutor(max_workers=10) as executor:
                    results = list(executor.map(check_logic, targets))
                    candidates = [r for r in results if r]

                if candidates:
                    candidates.sort(key=lambda x: (x['score'], x['vol']), reverse=True)
                    best = candidates[0]
                    s, p = best['symbol'], best['price']
                    
                    active_trades[s] = {'entry': p, 'highest_price': p, 'time': now.strftime('%H:%M:%S')}
                    
                    # إشعار الدخول المطور
                    sl = p * (1 - STOP_LOSS_PCT)
                    tp = p * (1 + ACTIVATION_PROFIT)
                    
                    msg = (
                        f"🔔 *دخول صفقة (نخبة)*\n━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `{s}` | ✨ *النقاط:* `{best['score']}/20`\n"
                        f"💰 *دخول:* `{p}` | 🛑 *وقف:* `{sl:.8f}`\n"
                        f"🎯 *هدف تفعيل:* `{tp:.8f}`\n"
                        f"⏰ *الوقت:* `{now.strftime('%H:%M:%S')}`\n━━━━━━━━━━━━━━"
                    )
                    send_telegram(msg)

            time.sleep(60)
        except: time.sleep(10)

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; trade = active_trades[s]
                if cp > trade['highest_price']: active_trades[s]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drop_from_peak = (trade['highest_price'] - cp) / trade['highest_price']
                
                exit_now = False
                reason = ""
                
                if gain <= -STOP_LOSS_PCT:
                    exit_now = True; reason = "STOP LOSS"
                elif gain >= ACTIVATION_PROFIT and drop_from_peak >= TRAILING_GAP:
                    exit_now = True; reason = "TRAILING TP"

                if exit_now:
                    pnl = gain * 100
                    send_telegram(f"🏁 *إغلاق صفقة ({reason})*\n🪙 `{s}`\n📊 النتيجة: `{pnl:+.2f}%`")
                    closed_today.append({'symbol': s, 'pnl': pnl})
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1)
                    del active_trades[s]
            time.sleep(10)
        except: time.sleep(5)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=keep_alive).start()
    Thread(target=monitor_trades).start()
    main_engine()
