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
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# --- 2. الإعدادات المالية ---
MAX_TRADES = 5
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

BLACKLIST = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'USDC/USDT', 'FDUSD/USDT']
VOL_MIN = 12000000
VOL_MAX = 450000000

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'timeout': 30000
})

active_trades = {}
daily_closed_trades = []
last_radar_15m = datetime.now() - timedelta(minutes=16)
last_open_report_1h = datetime.now()
last_closed_report_6h = datetime.now()

# --- 3. محرك التحليل (7 من 10) ---
def analyze_signal(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        close = df['c']
        
        # المؤشرات
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        rsi = 100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / close.diff().clip(upper=0).abs().rolling(14).mean().replace(0, 0.001))))
        
        macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        macd_h = macd - macd.ewm(span=9).mean()
        
        vol_avg = df['v'].iloc[-15:-1].mean()
        tr = (df['h'] - df['l']).rolling(14).mean()

        score = 0
        if close.iloc[-1] > ema50.iloc[-1]: score += 1
        if close.iloc[-1] > ema20.iloc[-1]: score += 1
        if 48 < rsi.iloc[-1] < 70: score += 1
        if macd_h.iloc[-1] > macd_h.iloc[-2]: score += 1
        if df['v'].iloc[-1] > vol_avg * 1.6: score += 1
        if close.iloc[-1] > df['o'].iloc[-1]: score += 1
        if rsi.iloc[-1] > rsi.iloc[-2]: score += 1
        if tr.iloc[-1] > tr.rolling(50).mean().iloc[-1]: score += 1
        if ema20.iloc[-1] > ema50.iloc[-1]: score += 1
        if rsi.iloc[-1] > 50: score += 1

        if score >= 7:
            return {'price': close.iloc[-1], 'score': score, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك الرئيسي ---
def main_engine():
    global last_radar_15m, last_open_report_1h, last_closed_report_6h
    send_telegram("✅ *v10.3 Ultra Sniper Fixed*\n- النظام يعمل الآن بـ 10 مؤشرات.")

    while True:
        try:
            now = datetime.now()

            # التتبع كل 10 ثوانٍ (6 مرات في الدقيقة)
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
                            daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'time': now, 'dur': str(now-trade['start']).split('.')[0]})
                            del active_trades[symbol]
                    except: continue
                time.sleep(10)

            # البحث عن صفقات
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                for s in potential[:80]:
                    if len(active_trades) >= MAX_TRADES: break
                    sig = analyze_signal(s)
                    if sig and sig['ready']:
                        active_trades[s] = {'entry': sig['price'], 'sl': sig['price']*0.97, 'highest_p': sig['price'], 'trailing_active': False, 'start': now}
                        send_telegram(f"💎 *Entry ({sig['score']}/10):* `{s}`")

            # التقارير
            if now >= last_radar_15m + timedelta(minutes=15):
                send_telegram(f"📡 *Radar:* النشطة `{len(active_trades)}/5`")
                last_radar_15m = now

            if now >= last_open_report_1h + timedelta(hours=1):
                msg = "📂 *Open Trades:*\n" + "\n".join([f"- `{s}`" for s in active_trades.keys()])
                send_telegram(msg if active_trades else "📂 لا صفقات مفتوحة.")
                last_open_report_1h = now

            if now >= last_closed_report_6h + timedelta(hours=6):
                msg = "📜 *Harvest:* " + str(len([t for t in daily_closed_trades if t['time'] >= now-timedelta(hours=6)])) + " صفقات."
                send_telegram(msg)
                last_closed_report_6h = now

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Active"
    
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
