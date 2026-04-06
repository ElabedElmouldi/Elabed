import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({
    'apiKey': os.environ.get('BINANCE_API_KEY', ''),
    'secret': os.environ.get('BINANCE_SECRET', ''),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# --- إعدادات المحفظة والتتبع (تعديلاتك الجديدة) ---
MAX_TRADES = 20            
TRADE_AMOUNT_USD = 10.0    
SCAN_INTERVAL = 300        
STOP_LOSS_PCT = 0.02       # ✅ وقف خسارة عند -2%
ACTIVATION_PROFIT = 0.04   # ✅ تنشيط التتبع عند +4%
TRAILING_GAP = 0.02        # ✅ فارق تتبع 2%

active_trades = {}
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك الفلترة (نظام الـ 20 شرطاً) ---
def get_breakout_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        score = 0
        
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        avg_v = df['v'].tail(20).mean()
        
        # شروط الانفجار
        if cp > ema20: score += 2
        if df['v'].iloc[-1] > avg_v * 2: score += 5
        if cp > df['h'].iloc[-2]: score += 3
        if cp > df['o'].iloc[-1]: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 3
        if ((cp - df['o'].iloc[-1])/df['o'].iloc[-1]) > 0.006: score += 5
        
        return score, cp
    except: return 0, 0

# --- 3. خيط المراقبة (تتبع 2% بعد ربح 4% ووقف -2%) ---
def monitor_thread():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                trade = active_trades[s]
                
                # تحديث القمة السعرية
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                
                highest = active_trades[s]['highest_price']
                gain = (cp - trade['entry']) / trade['entry']
                drop_from_peak = (highest - cp) / highest
                
                exit_now = False
                reason = ""

                # منطق الخروج
                if gain >= ACTIVATION_PROFIT and drop_from_peak >= TRAILING_GAP:
                    exit_now = True
                    reason = f"TRAILING TP (Peak: {gain*100:.2f}%)"
                elif gain <= -STOP_LOSS_PCT:
                    exit_now = True
                    reason = "STOP LOSS (-2%)"

                if exit_now:
                    pnl = gain * 100
                    send_telegram(f"🏁 *إغلاق صفقة:* `{s}`\nالسبب: `{reason}`\nالنتيجة: `{pnl:+.2f}%` ")
                    del active_trades[s]
            
            time.sleep(10)
        except: time.sleep(5)

# --- 4. المحرك الرئيسي (مسح 500 عملة ودخول تلقائي) ---
def main_engine():
    send_telegram(f"🚀 *تفعيل Sniper v80.0*\n🛡️ وقف خسارة: -2% | تتبع: 2% (بعد 4% ربح)\n💰 المحفظة: 20 صفقة × 10$")
    last_scan = datetime.now() - timedelta(minutes=10)

    while True:
        try:
            now = datetime.now()
            if now >= last_scan + timedelta(seconds=SCAN_INTERVAL):
                markets = exchange.fetch_markets()
                all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
                tickers = exchange.fetch_tickers(all_usdt)
                targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[20:520]

                with ThreadPoolExecutor(max_workers=15) as executor:
                    raw_results = list(executor.map(lambda s: {'symbol': s, 'data': get_breakout_score(s)}, targets))
                    results = [r for r in raw_results if r['data'][0] >= 12]

                results.sort(key=lambda x: x['data'][0], reverse=True)
                
                if results:
                    # تقرير أفضل 5
                    report = "🔝 *أفضل 5 عملات في المسح الحالي:*\n"
                    for i, res in enumerate(results[:5]):
                        report += f"{i+1}. `{res['symbol']}` ➔ سكور: `{res['data'][0]}/20`\n"
                    send_telegram(report)

                    # الدخول في المركز الأول (بدون تكرار)
                    best = results[0]
                    symbol = best['symbol']
                    if symbol not in active_trades and len(active_trades) < MAX_TRADES:
                        active_trades[symbol] = {
                            'entry': best['data'][1],
                            'highest_price': best['data'][1],
                            'time': now.strftime('%H:%M:%S')
                        }
                        send_telegram(f"🔔 *دخول تلقائي:* `{symbol}`\n💵 القيمة: `10$`\n📊 السكور: `{best['data'][0]}`")
                
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    main_engine()
