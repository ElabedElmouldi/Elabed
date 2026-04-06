import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية الجديدة ---
MAX_TRADES = 20               # تم التعديل لـ 20 صفقة
TRADE_AMOUNT = 25             # قيمة الصفقة 25 دولار
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.025        # تبكير التتبع قليلاً عند 2.5% لضمان الأرباح الصغيرة
TRAILING_CALLBACK = 0.01

BLACKLIST = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'USDC/USDT', 'FDUSD/USDT']
VOL_MIN = 10000000
VOL_MAX = 500000000

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
daily_closed_trades = []
last_open_report_1h = datetime.now()

# --- 3. محرك التحليل (شرط 8 من 10) ---
def analyze_v11(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        close = df['c']
        
        # المؤشرات العشرة
        ema50 = close.ewm(span=50).mean()
        ema20 = close.ewm(span=20).mean()
        rsi = 100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / close.diff().clip(upper=0).abs().rolling(14).mean().replace(0, 0.1))))
        macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        macd_h = macd - macd.ewm(span=9).mean()
        vol_avg = df['v'].iloc[-20:-1].mean()
        tr = (df['h'] - df['l']).rolling(14).mean()
        plus_dm = df['h'].diff().clip(lower=0).rolling(14).mean()
        adx = (plus_dm / tr.replace(0, 0.1) * 100)

        score = 0
        if close.iloc[-1] > ema50.iloc[-1]: score += 1               # 1
        if close.iloc[-1] > ema20.iloc[-1]: score += 1               # 2
        if 50 < rsi.iloc[-1] < 70: score += 1                        # 3
        if macd_h.iloc[-1] > macd_h.iloc[-2]: score += 1             # 4
        if df['v'].iloc[-1] > vol_avg * 1.5: score += 1              # 5
        if ema20.iloc[-1] > ema50.iloc[-1]: score += 1               # 6
        if close.iloc[-1] > df['o'].iloc[-1]: score += 1             # 7 (شمعة صاعدة)
        if adx.iloc[-1] > 25: score += 1                             # 8 (اتجاه قوي)
        if rsi.iloc[-1] > rsi.iloc[-2]: score += 1                   # 9 (زخم متزايد)
        if close.iloc[-1] > close.rolling(20).mean().iloc[-1]: score += 1 # 10

        if score >= 8: # المعيار الجديد: 8 من 10
            return {'price': close.iloc[-1], 'score': score, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_open_report_1h
    send_telegram("🎯 *v11.0 Strategic Hunter Active*\n- المعيار: `8/10 شروط`\n- المحفظة: `20 صفقة × 25$`\n- التحديث: `كل 10 ثوانٍ`")

    while True:
        try:
            now = datetime.now()

            # أ. التتبع النبضي (كل 10 ثوانٍ)
            for _ in range(6):
                for symbol in list(active_trades.keys()):
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        curr_p = ticker['last']
                        trade = active_trades[symbol]
                        
                        if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                        
                        if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                            trade['trailing_active'] = True
                            send_telegram(f"🚀 *Trailing:* `{symbol}`")

                        reason = ""
                        if not trade['trailing_active'] and curr_p <= trade['sl']: reason = "🛑 SL"
                        elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 TP"

                        if reason:
                            pnl = (curr_p - trade['entry']) / trade['entry']
                            send_telegram(f"{reason}: `{symbol}` ({pnl*100:+.2f}%)")
                            del active_trades[symbol]
                    except: continue
                time.sleep(10)

            # ب. فتح صفقات (حتى 20 صفقة)
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                for s in potential[:100]:
                    if len(active_trades) >= MAX_TRADES: break
                    sig = analyze_v11(s)
                    if sig and sig['ready']:
                        active_trades[s] = {
                            'entry': sig['price'], 
                            'sl': sig['price'] * (1 - STOP_LOSS_PCT), 
                            'highest_p': sig['price'], 
                            'trailing_active': False, 
                            'start_time': now.strftime("%H:%M:%S"),
                            'start_dt': now
                        }
                        send_telegram(f"💎 *Entry ({sig['score']}/10):* `{s}` (25$)")

            # ج. تقرير الساعة التفصيلي (المطلوب)
            if now >= last_open_report_1h + timedelta(hours=1):
                if active_trades:
                    report = "📂 *تقرير الصفقات المفتوحة (ساعة):*\n"
                    report += "----------------------------\n"
                    for s, d in active_trades.items():
                        cp = exchange.fetch_ticker(s)['last']
                        pnl = (cp - d['entry']) / d['entry'] * 100
                        duration = str(now - d['start_dt']).split('.')[0]
                        report += f"🔹 *{s}*\n- دخول: `{d['start_time']}` | مدة: `{duration}`\n- السعر: `{d['entry']}` ➔ `{cp}`\n- الربح: `{pnl:+.2f}%`\n\n"
                    send_telegram(report)
                else:
                    send_telegram("📂 لا توجد صفقات مفتوحة حالياً.")
                last_open_report_1h = now

        except: time.sleep(15)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Hunter v11.0 | Active: {len(active_trades)}/20"
    
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
