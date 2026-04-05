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
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: pass

# --- 2. الإعدادات المالية والفنية ---
MAX_TRADES = 10
TRADE_AMOUNT = 50
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

VOL_MIN = 15000000
VOL_MAX = 550000000

exchange = ccxt.binance({'enableRateLimit': True})

# جداول المواعيد والبيانات
active_trades = {}
daily_closed_trades = []
last_radar_15m = datetime.now()
last_open_report_1h = datetime.now()
last_closed_report_6h = datetime.now()

# --- 3. محرك التحليل (الخماسي) ---
def analyze_signal_v9(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=70)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # المؤشرات
        df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
        df['ma20'] = df['c'].rolling(20).mean()
        df['std'] = df['c'].rolling(20).std()
        width = (df['std'] * 4) / df['ma20']
        
        # RSI & MACD
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        exp1 = df['c'].ewm(span=12, adjust=False).mean()
        exp2 = df['c'].ewm(span=26, adjust=False).mean()
        hist = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
        
        vol_avg = df['v'].iloc[-10:-1].mean()
        vol_now = df['v'].iloc[-1]

        # الشروط
        price_now = df['c'].iloc[-1]
        if price_now > df['ema50'].iloc[-1] and \
           width.iloc[-1] < width.rolling(50).min().iloc[-1] * 1.2 and \
           vol_now > (vol_avg * 1.8) and \
           50 < rsi < 69 and \
           hist.iloc[-1] > hist.iloc[-2]:
            return {'price': price_now, 'rsi': rsi, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي المجدول ---
def main_engine():
    global last_radar_15m, last_open_report_1h, last_closed_report_6h
    send_telegram("🚀 *تشغيل النسخة المجدولة v9.2*\n- المحفظة: `10 صفقات × 50$`\n- التقارير: `رادار (15د) | مفتوحة (1س) | مغلقة (6س)`")

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة وإغلاق الصفقات (تحديث مستمر)
            for symbol in list(active_trades.keys()):
                curr_p = exchange.fetch_ticker(symbol)['last']
                trade = active_trades[symbol]
                if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                
                if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                    trade['trailing_active'] = True
                    send_telegram(f"🎯 *تفعيل التتبع:* `{symbol}`")

                close_reason = ""
                if not trade['trailing_active'] and curr_p <= trade['sl']: close_reason = "🛑 وقف خسارة"
                elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): close_reason = "💰 جني أرباح"

                if close_reason:
                    pnl = (curr_p - trade['entry']) / trade['entry']
                    duration = str(now - trade['start']).split('.')[0]
                    send_telegram(f"{close_reason}: `{symbol}`\n📊 النتيجة: `{pnl*100:+.2f}%`\n⏱️ المدة: `{duration}`")
                    daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'duration': duration, 'time': now})
                    del active_trades[symbol]

            # ب. فتح صفقات جديدة (حتى 10)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                symbols = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:300]
                for s in symbols:
                    if len(active_trades) >= MAX_TRADES or s in active_trades: break
                    sig = analyze_signal_v9(s)
                    if sig and sig['ready']:
                        active_trades[s] = {'entry': sig['price'], 'sl': sig['price']*0.97, 'highest_p': sig['price'], 'trailing_active': False, 'start': now}
                        send_telegram(f"🚀 *دخول جديد:* `{s}` بسعر `{sig['price']}`")

            # ج. رادار الـ 15 دقيقة (قائمة 20 عملة)
            if now >= last_radar_15m + timedelta(minutes=15):
                all_tickers = exchange.fetch_tickers()
                potential = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:300]
                radar_list = []
                for s in potential:
                    res = analyze_signal_v9(s)
                    if res and res['ready']: radar_list.append(f"- `{s}` (RSI: {res['rsi']:.1f})")
                
                if radar_list:
                    send_telegram(f"🔍 *رادار الـ 15 دقيقة (أفضل الفرص):*\n" + "\n".join(radar_list[:20]))
                last_radar_15m = now

            # د. تقرير الساعة (الصفقات المفتوحة فقط)
            if now >= last_open_report_1h + timedelta(hours=1):
                msg = f"📂 *تقرير الصفقات المفتوحة ({now.strftime('%H:%M')})*\n"
                if active_trades:
                    for s, d in active_trades.items():
                        cp = exchange.fetch_ticker(s)['last']
                        pnl = (cp - d['entry']) / d['entry'] * 100
                        msg += f"- `{s}`: `{pnl:+.2f}%` (دخول: `{d['entry']}`)\n"
                else: msg += "لا توجد صفقات مفتوحة حالياً."
                send_telegram(msg)
                last_open_report_1h = now

            # هـ. تقرير الـ 6 ساعات (الصفقات المغلقة)
            if now >= last_closed_report_6h + timedelta(hours=6):
                msg = f"📜 *تقرير الحصاد (آخر 6 ساعات)*\n"
                # تصفية الصفقات التي أغلقت في آخر 6 ساعات فقط
                recent_closed = [t for t in daily_closed_trades if t['time'] >= now - timedelta(hours=6)]
                if recent_closed:
                    total_pnl = sum([t['pnl'] for t in recent_closed])
                    for t in recent_closed:
                        msg += f"- `{t['symbol']}` | `{t['pnl']*100:+.2f}%` | `{t['duration']}`\n"
                    msg += f"\n📈 صافي الربح للفترة: `{total_pnl*100:+.2f}%`"
                else: msg += "لم يتم إغلاق أي صفقات في هذه الفترة."
                send_telegram(msg)
                last_closed_report_6h = now

            time.sleep(30)
        except: time.sleep(20)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Sniper v9.2 Scheduled Active"
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    main_engine()
