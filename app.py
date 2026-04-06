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

# --- 2. إعدادات الأداء والتتبع (حسب طلبك) ---
MAX_TRADES = 10            
TRADE_AMOUNT_USD = 100.0   
ACTIVATION_PROFIT = 0.03   # ✅ يبدأ التتبع عند ربح 3%
TRAILING_GAP = 0.015       # ✅ يغلق الصفقة عند تراجع 1.5% من القمة
STOP_LOSS_PCT = 0.035      # وقف خسارة حماية 3.5%
SCAN_COUNT = 600           # مسح 600 عملة

active_trades = {}    
closed_today = []     
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. محرك تحليل السوق (600 عملة) ---
def analyze_market(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        
        score = 0
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        
        # شروط الدخول (سيولة + اتجاه)
        if cp > ema20: score += 10
        if df['v'].iloc[-1] > df['v'].tail(15).mean() * 1.8: score += 10
        
        return {'symbol': symbol, 'score': score, 'price': cp} if score >= 20 else None
    except: return None

# --- 4. خيط المراقبة اللحظية (التتبع 1.5% من 3%) ---
def monitor_thread():
    while True:
        try:
            # تصفير سجل اليوم عند منتصف الليل
            if datetime.now().hour == 0 and datetime.now().minute == 0 and datetime.now().second < 15:
                global closed_today; closed_today = []

            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                trade = active_trades[symbol]
                
                # تحديث أعلى سعر وصلت له العملة منذ الدخول
                if cp > trade['highest_price']: 
                    active_trades[symbol]['highest_price'] = cp
                
                highest = active_trades[symbol]['highest_price']
                current_gain = (cp - trade['entry']) / trade['entry']
                drop_from_peak = (highest - cp) / highest
                
                exit_now = False
                reason = ""

                # تطبيق منطق التتبع المطلوب:
                if current_gain >= ACTIVATION_PROFIT:
                    # إذا تحقق شرط الـ 3%، نراقب التراجع بمقدار 1.5%
                    if drop_from_peak >= TRAILING_GAP:
                        exit_now = True
                        reason = "TRAILING EXIT (1.5% Drop)"
                elif current_gain <= -STOP_LOSS_PCT:
                    # وقف الخسارة العادي إذا لم تصل للهدف
                    exit_now = True
                    reason = "STOP LOSS"

                if exit_now:
                    pnl_val = current_gain * 100
                    closed_today.append({
                        'symbol': symbol, 'pnl': pnl_val,
                        'time_in': trade['time'], 'time_out': datetime.now().strftime('%H:%M')
                    })
                    send_telegram(f"🏁 *إغلاق صفقة:* `{symbol}`\nالسبب: `{reason}`\nالنتيجة: `{pnl_val:+.2f}%` ")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(5)

# --- 5. التقارير الساعية المدمجة ---
def send_hourly_report():
    now_str = datetime.now().strftime('%H:%M')
    report = f"📊 *تقرير الأداء الساعي ({now_str})*\n━━━━━━━━━━━━━━\n"
    
    # الصفقات المفتوحة
    report += "🟢 *الصفقات المفتوحة:*\n"
    if not active_trades: report += "_لا يوجد_\n"
    for s, d in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(s); cp = ticker['last']
            pnl = ((cp - d['entry']) / d['entry']) * 100
            report += f"`{s}`: `{pnl:+.2f}%` (🔝 `{(d['highest_price']-d['entry'])/d['entry']*100:+.1f}%`)\n"
        except: pass

    # الصفقات المغلقة اليوم
    report += f"\n✅ *إغلاقات اليوم ({len(closed_today)}):*\n"
    if closed_today:
        total_pnl = sum(t['pnl'] for t in closed_today)
        report += f"📈 *صافي الربح اليومي:* `{total_pnl:+.2f}%`"
    else: report += "_لا يوجد إغلاقات بعد._"
    
    send_telegram(report)

# --- 6. المحرك الرئيسي (مسح 600 عملة) ---
def main_engine():
    send_telegram(f"🚀 *Sniper v55.0 Active*\n🔍 رادار 600 عملة\n🛡️ تتبع: 1.5% (بعد 3% ربح)")
    last_scan = datetime.now() - timedelta(minutes=15)
    last_report = datetime.now()

    while True:
        try:
            now = datetime.now()
            
            # تقرير كل ساعة
            if now >= last_report + timedelta(hours=1):
                send_hourly_report()
                last_report = now

            # مسح كل 10 دقائق
            if now >= last_scan + timedelta(minutes=10):
                send_telegram("🔍 *جاري مسح 600 عملة USDT...*")
                markets = exchange.fetch_markets()
                all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
                tickers = exchange.fetch_tickers(all_usdt)
                targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[20:620]
                
                with ThreadPoolExecutor(max_workers=12) as executor:
                    results = [r for r in list(executor.map(analyze_market, targets)) if r]

                results.sort(key=lambda x: x['score'], reverse=True)
                
                for res in results:
                    if len(active_trades) < MAX_TRADES and res['symbol'] not in active_trades:
                        bal = exchange.fetch_balance()
                        if bal['free'].get('USDT', 0) >= TRADE_AMOUNT_USD:
                            s = res['symbol']
                            active_trades[s] = {
                                'entry': res['price'], 'highest_price': res['price'],
                                'time': now.strftime('%H:%M:%S')
                            }
                            send_telegram(f"🔔 *دخول جديد:* `{s}`\n💰 السعر: `{res['price']}`\n🛡️ تتبع 1.5% مفعل (بعد ربح 3%)")
                
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    main_engine()
