import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية والتقنية ---
MAX_TRADES = 10           # أقصى عدد صفقات متزامنة
ACTIVATION_PROFIT = 0.05   # تفعيل التتبع بعد ربح 5%
TRAILING_GAP = 0.02        # مسافة التتبع (2%)
STOP_LOSS_PCT = 0.04       # وقف خسارة ثابت 4%

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    # الصفقات القائمة
closed_today = []     # سجل الصفقات المغلقة اليوم

# --- 3. وظيفة تقارير الصفقات (المفتوحة والمغلقة) ---
def send_combined_hourly_report():
    now_str = datetime.now().strftime('%H:%M')
    
    # أولاً: تقرير الصفقات المفتوحة
    open_report = f"📊 *تقرير الصفقات المفتوحة ({now_str})*\n━━━━━━━━━━━━━━\n"
    if not active_trades:
        open_report += "_لا توجد صفقات مفتوحة حالياً._\n"
    else:
        for symbol, data in active_trades.items():
            try:
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                pnl = ((cp - data['entry']) / data['entry']) * 100
                emoji = "📈" if pnl >= 0 else "📉"
                open_report += (
                    f"🪙 *{symbol}*\n"
                    f"📥 دخول: `{data['entry']}` | الحالي: `{cp}`\n"
                    f"{emoji} النسبة: `{pnl:+.2f}%` | ⏰: `{data['time']}`\n"
                    f"┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                )
            except: pass

    # ثانياً: تقرير الصفقات المغلقة اليوم
    closed_report = f"\n✅ *العمليات المنتهية اليوم*\n━━━━━━━━━━━━━━\n"
    if not closed_today:
        closed_report += "_لم يتم إغلاق أي صفقات اليوم بعد._\n"
    else:
        daily_total = 0
        for trade in closed_today:
            emoji = "💰" if trade['pnl'] > 0 else "🛑"
            closed_report += (
                f"{emoji} `{trade['symbol']}`: `{trade['pnl']:+.2f}%` "
                f"({trade['time_in']} -> {trade['time_out']})\n"
            )
            daily_total += trade['pnl']
        closed_report += f"━━━━━━━━━━━━━━\n📈 *صافي أداء اليوم:* `{daily_total:+.2f}%`"

    send_telegram(open_report + closed_report)

# --- 4. خوارزمية المسح والتحليل (v20) ---
def analyze_market(symbol, ticker):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=40)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        c = df['c']
        ema20 = c.ewm(span=20).mean()
        
        score = 0
        # معايير السيولة والزخم
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2.5: score += 10
        if c.iloc[-1] > ema20.iloc[-1] * 1.01: score += 10
        
        return {'symbol': symbol, 'score': score, 'price': ticker['last']} if score >= 20 else None
    except: return None

# --- 5. خيط المراقبة اللحظية (تتبع السعر كل 10 ثوانٍ) ---
def monitor_thread():
    while True:
        try:
            # تصفير السجل عند منتصف الليل
            if datetime.now().hour == 0 and datetime.now().minute == 0 and datetime.now().second < 15:
                global closed_today
                closed_today = []

            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                trade = active_trades[symbol]
                
                # تحديث القمة
                if cp > trade['highest_price']: active_trades[symbol]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                highest = active_trades[symbol]['highest_price']
                drop = (highest - cp) / highest
                
                trigger_exit = False
                reason = ""

                if gain <= -STOP_LOSS_PCT:
                    trigger_exit = True; reason = "STOP LOSS"
                elif gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP:
                    trigger_exit = True; reason = "TRAILING TP"

                if trigger_exit:
                    pnl_val = gain * 100
                    closed_today.append({
                        'symbol': symbol, 'entry': trade['entry'], 'exit': cp,
                        'time_in': trade['time'], 'time_out': datetime.now().strftime('%H:%M'),
                        'pnl': pnl_val
                    })
                    send_telegram(f"🏁 *إغلاق صفقة ({reason}):* `{symbol}`\nالنتيجة: `{pnl_val:+.2f}%`")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(5)

# --- 6. المحرك الرئيسي (مسح 900 عملة + تقرير ساعي) ---
def main_engine():
    send_telegram("🚀 *تم تشغيل نظام Sniper v16.5*\n- مسح 900 عملة\n- تتبع 2%\n- تقارير ساعية شاملة")
    last_scan = datetime.now() - timedelta(minutes=15)
    last_report = datetime.now()

    while True:
        try:
            now = datetime.now()
            
            # 1. إرسال التقارير كل ساعة
            if now >= last_report + timedelta(hours=1):
                send_combined_hourly_report()
                last_report = now

            # 2. المسح التوربيني لـ 900 عملة
            if now >= last_scan + timedelta(minutes=10):
                tickers = exchange.fetch_tickers()
                all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
                targets = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
                
                for s in targets:
                    if len(active_trades) < MAX_TRADES and s not in active_trades:
                        res = analyze_market(s, tickers[s])
                        if res:
                            p = res['price']
                            active_trades[s] = {'entry': p, 'highest_price': p, 'time': now.strftime('%H:%M:%S')}
                            send_telegram(f"🔔 *إشارة دخول:* `{s}`\nالسعر: `{p}`\nالهدف: تتبع `>5%` بمساحة `2%`")
                    time.sleep(0.04)
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    # تشغيل سيرفر وهمي للحفاظ على العمل
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    # تشغيل خيوط المراقبة والمسح
    Thread(target=monitor_thread).start()
    main_engine()
