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

# --- 1. الإعدادات والروابط ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
# استبدل هذا بالرابط الذي سيعطيك إياه Render بعد الرفع
WEB_URL = "https://your-app-name.onrender.com" 

# الإعدادات المالية
MAX_TRADES = 10
TRADE_VALUE_USD = 100
ACTIVATION_PROFIT = 0.05 
TRAILING_GAP = 0.02      
STOP_LOSS_PCT = 0.04     

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
closed_today = []     
blacklist_coins = {} 
START_TIME = datetime.now()

# --- 2. نظام Flask للبقاء مستيقظاً (Web Server) ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"Sniper v20.0 is Active. Running since: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/health')
def health():
    return "OK", 200

def keep_alive():
    """ دالة النبض لإبقاء السيرفر مستيقظاً """
    time.sleep(30) # انتظار بدء التشغيل
    while True:
        try:
            # إرسال طلب لنفسه كل 10 دقائق
            requests.get(WEB_URL, timeout=10)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Render Heartbeat Sent.")
        except:
            print("Heartbeat failed, retrying later...")
        time.sleep(600)

# --- 3. وظائف التلجرام والتحليل v20 ---

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def analyze_coin(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=30)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        last_change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if last_change > 7.0: return 0 # فلترة الـ Pump
        
        score = 0
        if df['v'].iloc[-1] > df['v'].iloc[-10:-1].mean() * 2.5: score += 10
        if df['c'].iloc[-1] > df['c'].ewm(span=20).mean().iloc[-1]: score += 10
        return score
    except: return 0

# --- 4. المحرك الرئيسي (المسح والمراقبة) ---

def scan_and_trade():
    global blacklist_coins
    send_telegram("🚀 *Sniper v20.0 Deployed on Render*\nنظام الحماية والنبض مفعّل.")
    
    while True:
        try:
            # تنظيف القائمة السوداء (Blacklist)
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}

            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                targets = sorted([s for s in tickers.keys() if '/USDT' in s], 
                                key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
                
                def check_logic(s):
                    if s not in active_trades and s not in blacklist_coins:
                        score = analyze_coin(s)
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
                    
                    sl = p * (1 - STOP_LOSS_PCT)
                    tp = p * (1 + ACTIVATION_PROFIT)
                    
                    msg = (
                        f"🔔 *دخول صفقة (النخبة)*\n"
                        f"🪙 *العملة:* `{s}` | ✨ *النقاط:* `{best['score']}/20`\n"
                        f"💰 *السعر:* `{p}` | 🛑 *الوقف:* `{sl:.8f}`\n"
                        f"🎯 *الهدف:* `{tp:.8f}` | ⏰ `{now.strftime('%H:%M:%S')}`"
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
                drop = (trade['highest_price'] - cp) / trade['highest_price']
                
                if gain <= -STOP_LOSS_PCT or (gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP):
                    pnl = gain * 100
                    send_telegram(f"🏁 *خروج:* `{s}`\nالنتيجة: `{pnl:+.2f}%`")
                    closed_today.append({'symbol': s, 'pnl': pnl})
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1)
                    del active_trades[s]
            time.sleep(10)
        except: time.sleep(5)

# --- 5. التشغيل النهائي ---

if __name__ == "__main__":
    # تشغيل السيرفر (Flask)
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    
    # تشغيل النبض للبقاء مستيقظاً
    Thread(target=keep_alive).start()
    
    # تشغيل المراقبة
    Thread(target=monitor_trades).start()
    
    # تشغيل المحرك الرئيسي
    scan_and_trade()
