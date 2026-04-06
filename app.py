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

# --- إعدادات المحفظة (تعديلاتك الجديدة) ---
MAX_TRADES = 10            # 10 صفقات
TRADE_AMOUNT_USD = 100.0   # 100 دولار لكل صفقة
SCAN_INTERVAL = 300        
STOP_LOSS_PCT = 0.02       # وقف خسارة -2%
ACTIVATION_PROFIT = 0.04   # تنشيط التتبع عند +4%
TRAILING_GAP = 0.02        # فارق تتبع 2%

# نظام تتبع قيمة المحفظة
wallet_balance = 1000.0    # القيمة الابتدائية للمحفظة
active_trades = {}
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك الفلترة (20 شرطاً) ---
def get_breakout_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]; score = 0
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        avg_v = df['v'].tail(20).mean()
        
        if cp > ema20: score += 2
        if df['v'].iloc[-1] > avg_v * 2: score += 5
        if cp > df['h'].iloc[-2]: score += 3
        if cp > df['o'].iloc[-1]: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 3
        if ((cp - df['o'].iloc[-1])/df['o'].iloc[-1]) > 0.006: score += 5
        
        return score, cp
    except: return 0, 0

# --- 3. خيط المراقبة وتحديث المحفظة ---
def monitor_thread():
    global wallet_balance
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                trade = active_trades[s]
                
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                
                highest = active_trades[s]['highest_price']
                gain = (cp - trade['entry']) / trade['entry']
                drop = (highest - cp) / highest
                
                exit_now = False
                reason = ""

                if gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP:
                    exit_now = True; reason = "تتبع الربح (Trailing)"
                elif gain <= -STOP_LOSS_PCT:
                    exit_now = True; reason = "وقف الخسارة (-2%)"

                if exit_now:
                    pnl_percent = gain * 100
                    pnl_usd = TRADE_AMOUNT_USD * gain
                    wallet_balance += pnl_usd # تحديث الرصيد الإجمالي
                    
                    status_emoji = "💰" if pnl_usd > 0 else "🛑"
                    report = (
                        f"{status_emoji} *تم إغلاق صفقة:* `{s}`\n"
                        f"━ السبب: `{reason}`\n"
                        f"━ الربح/الخسارة: `{pnl_percent:+.2f}%` (`{pnl_usd:+.2f}$`)\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"🏦 *قيمة المحفظة الحالية:* `{wallet_balance:.2f}$`"
                    )
                    send_telegram(report)
                    del active_trades[s]
            
            time.sleep(10)
        except: time.sleep(5)

# --- 4. المحرك الرئيسي ---
def main_engine():
    send_telegram(f"🛡️ *تشغيل v85.0*\n🎯 النظام: 10 صفقات × 100$\n💰 المحفظة الابتدائية: `{wallet_balance}$` ")
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
                    top_5 = "🔝 *أفضل 5 عملات مكتشفة:*\n"
                    for i, res in enumerate(results[:5]):
                        top_5 += f"{i+1}. `{res['symbol']}` ➔ `{res['data'][0]}/20`\n"
                    send_telegram(top_5)

                    # الدخول التلقائي
                    best = results[0]
                    symbol = best['symbol']
                    if symbol not in active_trades and len(active_trades) < MAX_TRADES:
                        active_trades[symbol] = {
                            'entry': best['data'][1],
                            'highest_price': best['data'][1],
                            'time': now.strftime('%H:%M:%S')
                        }
                        send_telegram(f"🔔 *دخول جديد:* `{symbol}`\n💵 الاستثمار: `100$`\n📊 السكور: `{best['data'][0]}`")
                
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    main_engine()
