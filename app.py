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

# الثوابت المالية (دخول بـ 100$ من أصل 1000$)
TRADE_AMOUNT_USD = 100.0   
MAX_TRADES = 10            
ACTIVATION_PROFIT = 0.03   # التنشيط عند 3%
TRAILING_GAP = 0.015       # فارق التتبع 1.5%
STOP_LOSS_PCT = 0.035      # وقف خسارة 3.5%
MONITOR_INTERVAL = 10      # فحص كل 10 ثوانٍ

active_trades = {}    
closed_today = []     
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك السكور الفني (نظام الـ 20 شرطاً) ---
def calculate_advanced_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]; score = 0
        
        # المتوسطات والزخم
        ema20 = df['c'].ewm(span=20).mean(); ema50 = df['c'].ewm(span=50).mean()
        delta = df['c'].diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (g / l))).iloc[-1]

        # توزيع النقاط (الاتجاه، السيولة، الزخم)
        if cp > ema20.iloc[-1]: score += 4
        if ema20.iloc[-1] > ema50.iloc[-1]: score += 4
        if 50 < rsi < 75: score += 4
        if df['v'].iloc[-1] > df['v'].tail(15).mean() * 1.8: score += 5 # انفجار سيولة
        if cp > df['o'].iloc[-1]: score += 3
        
        return score, cp, ((cp - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
    except: return 0, 0, 0

# --- 3. مراقبة الصفقات اللحظية (تتبع 1.5% كل 10ث) ---
def monitor_thread():
    while True:
        try:
            if datetime.now().hour == 0 and datetime.now().minute == 0 and datetime.now().second < 15:
                global closed_today; closed_today = []

            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; tr = active_trades[s]
                if cp > tr.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                
                gain = (cp - tr['entry']) / tr['entry']
                drop = (tr['highest_price'] - cp) / tr['highest_price']
                
                exit_now = False; reason = ""
                if gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP:
                    exit_now = True; reason = "TRAILING EXIT (1.5%)"
                elif gain <= -STOP_LOSS_PCT:
                    exit_now = True; reason = "STOP LOSS"

                if exit_now:
                    pnl_val = gain * 100
                    closed_today.append({'symbol': s, 'pnl': pnl_val, 'time': datetime.now().strftime('%H:%M')})
                    send_telegram(f"🏁 *إغلاق صفقة:* `{s}`\nالسبب: `{reason}`\nالنتيجة: `{pnl_val:+.2f}%` ")
                    del active_trades[s]
            time.sleep(MONITOR_INTERVAL)
        except: time.sleep(5)

# --- 4. التقارير الساعية ---
def send_combined_report():
    now_str = datetime.now().strftime('%H:%M')
    report = f"📊 *تقرير الأداء ({now_str})*\n━━━━━━━━━━━━━━\n"
    if not active_trades:
        report += "_لا توجد صفقات حالية._\n"
    else:
        for s, d in active_trades.items():
            try:
                ticker = exchange.fetch_ticker(s); cp = ticker['last']
                pnl = ((cp - d['entry']) / d['entry']) * 100
                report += f"🪙 `{s}`: `{pnl:+.2f}%` | 📥 `{d['entry']}`\n"
            except: pass
    
    if closed_today:
        daily_pnl = sum(t['pnl'] for t in closed_today)
        report += f"\n✅ *عمليات اليوم:* `{len(closed_today)}`\n📈 *صافي اليوم:* `{daily_pnl:+.2f}%`"
    
    send_telegram(report)

# --- 5. المحرك الرئيسي (مسح 600 عملة) ---
def main_engine():
    send_telegram(f"🛡️ *تشغيل v53.0 (الرادار العملاق)*\n🔍 مسح 600 عملة USDT\n🎯 تتبع 1.5% بعد ربح 3%")
    last_report = datetime.now()
    
    while True:
        try:
            now = datetime.now()
            if now >= last_report + timedelta(hours=1):
                send_combined_report()
                last_report = now

            send_telegram("🔍 *جاري فحص 600 عملة الآن...*")
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
            tickers = exchange.fetch_tickers(all_usdt)
            # ترتيب حسب السيولة واختيار 600 عملة (تخطي أول 20 عملة كبرى)
            targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[20:620]

            # استخدام 12 خيط معالجة للسرعة مع 600 عملة
            with ThreadPoolExecutor(max_workers=12) as exec:
                def scan(s):
                    if s not in active_trades:
                        sc, pr, ch = calculate_advanced_score(s)
                        return {'symbol': s, 'score': sc, 'price': pr} if sc >= 15 else None
                    return None
                results = [r for r in list(exec.map(scan, targets)) if r]

            results.sort(key=lambda x: x['score'], reverse=True)
            
            if results and len(active_trades) < MAX_TRADES:
                best = results[0]
                if best['score'] >= 17: # الدخول فقط في أقوى الفرص
                    active_trades[best['symbol']] = {
                        'entry': best['price'], 
                        'highest_price': best['price'],
                        'time': now.strftime('%H:%M:%S')
                    }
                    send_telegram(f"🔔 *إشارة دخول:* `{best['symbol']}`\n💰 السعر: `{best['price']}`\n📊 السكور: `{best['score']}/20` \n🛡️ تتبع: 3% + 1.5%")

            time.sleep(600) # مسح كل 10 دقائق
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    main_engine()
