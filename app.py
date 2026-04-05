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

# --- 2. الإعدادات المالية (5 صفقات × 100$) ---
MAX_TRADES = 5
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

VOL_MIN = 10000000
VOL_MAX = 600000000

exchange = ccxt.binance({'enableRateLimit': True})

# المواعيد
active_trades = {}
daily_closed_trades = []
last_radar_15m = datetime.now() - timedelta(minutes=16)
last_open_report_1h = datetime.now()
last_closed_report_6h = datetime.now()

# --- 3. محرك التحليل "المرن" (منطق 3 من 5) ---
def analyze_signal_flexible(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=70)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # حساب المؤشرات الـ 5
        # [1] EMA 50
        ema50 = df['c'].ewm(span=50, adjust=False).mean().iloc[-1]
        # [2] Bollinger Squeeze
        df['std'] = df['c'].rolling(20).std()
        df['ma20'] = df['c'].rolling(20).mean()
        width = (df['std'] * 4) / df['ma20']
        # [3] RSI
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        # [4] MACD Hist
        exp1 = df['c'].ewm(span=12, adjust=False).mean()
        exp2 = df['c'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        hist = macd - macd.ewm(span=9, adjust=False).mean()
        # [5] Volume
        vol_avg = df['v'].iloc[-10:-1].mean()
        vol_now = df['v'].iloc[-1]

        # فحص الشروط الـ 5 (True/False)
        c1 = df['c'].iloc[-1] > ema50                         # السعر فوق المتوسط
        c2 = width.iloc[-1] < width.rolling(50).mean().iloc[-1] # وجود ضغط سعري
        c3 = 45 < rsi < 70                                    # زخم معتدل
        c4 = hist.iloc[-1] > hist.iloc[-2]                    # تسارع إيجابي
        c5 = vol_now > (vol_avg * 1.5)                        # سيولة جيدة

        # حساب عدد الشروط المحققة
        score = sum([c1, c2, c3, c4, c5])
        
        if score >= 3: # يكفي توفر 3 شروط من أصل 5
            return {'price': df['c'].iloc[-1], 'score': score, 'rsi': rsi, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_radar_15m, last_open_report_1h, last_closed_report_6h
    send_telegram("⚡ *v9.4 Agile Sniper Active*\n- القاعدة: `3 من أصل 5 شروط`\n- الهدف: `اقتناص أسرع للفرص`")

    while True:
        try:
            now = datetime.now()

            # أ. المراقبة والملاحقة (مستمر)
            for symbol in list(active_trades.keys()):
                curr_p = exchange.fetch_ticker(symbol)['last']
                trade = active_trades[symbol]
                if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                
                if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                    trade['trailing_active'] = True
                    send_telegram(f"🎯 *تفعيل التتبع:* `{symbol}`")

                reason = ""
                if not trade['trailing_active'] and curr_p <= trade['sl']: reason = "🛑 وقف خسارة"
                elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 جني أرباح"

                if reason:
                    pnl = (curr_p - trade['entry']) / trade['entry']
                    send_telegram(f"{reason}: `{symbol}` ({pnl*100:+.2f}%)")
                    daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'duration': str(now-trade['start']).split('.')[0], 'time': now})
                    del active_trades[symbol]

            # ب. فتح صفقات (5 صفقات بـ 100$)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                potential = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:250]
                for s in potential:
                    if len(active_trades) >= MAX_TRADES or s in active_trades: break
                    sig = analyze_signal_flexible(s)
                    if sig and sig['ready']:
                        active_trades[s] = {'entry': sig['price'], 'sl': sig['price']*0.97, 'highest_p': sig['price'], 'trailing_active': False, 'start': now}
                        send_telegram(f"🚀 *دخول:* `{s}` (نقاط القوة: `{sig['score']}/5`)")

            # ج. رادار الـ 15 دقيقة (سيصلك الآن بانتظام)
            if now >= last_radar_15m + timedelta(minutes=15):
                all_tickers = exchange.fetch_tickers()
                potential = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:250]
                radar_list = []
                for s in potential:
                    res = analyze_signal_flexible(s)
                    if res and res['ready']: radar_list.append(f"- `{s}` (قوة الإشارة: `{res['score']}/5`)")
                
                if radar_list:
                    send_telegram(f"🔍 *رادار الـ 15 دقيقة (فرص متاحة):*\n" + "\n".join(radar_list[:20]))
                else:
                    send_telegram("📡 *تحديث الرادار:* تم الفحص، لا توجد فرص محققة لـ 3 شروط حالياً.")
                last_radar_15m = now

            # د. التقارير الدورية (ساعة و 6 ساعات)
            # ... [نفس منطق التقارير المعتاد] ...

            time.sleep(35)
        except: time.sleep(20)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Agile Sniper v9.4 | Trades: {len(active_trades)}/5"
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    main_engine()
