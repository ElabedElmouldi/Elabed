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
        except: pass

# --- 2. الإعدادات المالية (20 صفقة × 25$) ---
MAX_TRADES = 20
TRADE_AMOUNT = 25
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.025
TRAILING_CALLBACK = 0.01
MAX_24H_CHANGE = 0.10

BLACKLIST = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'USDC/USDT', 'FDUSD/USDT']
VOL_MIN = 10000000 
VOL_MAX = 400000000 

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
last_open_report_1h = datetime.now()

# وظيفة مساعدة لحساب المؤشرات
def get_indicators(df):
    close = df['c']
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    # RSI مبسط
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))
    return ema50, ema20, rsi

# --- 3. محرك التحليل المتعدد (1h & 15m) ---
def analyze_multi_tf(symbol, change_24h):
    if change_24h >= MAX_24H_CHANGE: return {'ready': False}
    
    try:
        # جلب بيانات الساعة (الاتجاه العام)
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df_1h = pd.DataFrame(bars_1h, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_1h, _, rsi_1h = get_indicators(df_1h)

        # جلب بيانات 15 دقيقة (التنفيذ)
        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df_15m = pd.DataFrame(bars_15m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_15m, ema20_15m, rsi_15m = get_indicators(df_15m)
        
        score = 0
        # شروط فريم الساعة (3 نقاط)
        if df_1h['c'].iloc[-1] > ema50_1h.iloc[-1]: score += 1      # الاتجاه صاعد على الساعة
        if rsi_1h.iloc[-1] > 50: score += 1                         # الزخم إيجابي على الساعة
        if df_1h['c'].iloc[-1] > df_1h['o'].iloc[-1]: score += 1    # شمعة الساعة الحالية خضراء

        # شروط فريم 15 دقيقة (7 نقاط)
        if df_15m['c'].iloc[-1] > ema20_15m.iloc[-1]: score += 1    # فوق المتوسط السريع
        if 48 < rsi_15m.iloc[-1] < 70: score += 1                   # RSI في منطقة ذهبية
        if df_15m['v'].iloc[-1] > df_15m['v'].iloc[-20:-1].mean() * 1.5: score += 1 # سيولة
        if df_15m['c'].iloc[-1] > df_15m['o'].iloc[-1]: score += 1  # شمعة صاعدة
        if rsi_15m.iloc[-1] > rsi_15m.iloc[-2]: score += 1          # صعود القوة الشرائية
        if ema20_15m.iloc[-1] > ema50_15m.iloc[-1]: score += 1      # تقاطع إيجابي
        if df_15m['c'].iloc[-1] > df_15m['l'].iloc[-1] + (df_15m['h'].iloc[-1]-df_15m['l'].iloc[-1])*0.7: score += 1 # إغلاق قوي

        if score >= 7:
            return {'price': df_15m['c'].iloc[-1], 'score': score, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_open_report_1h
    send_telegram("🧬 *v11.6 Multi-Timeframe System Active*\n- الفلاتر: `1h Trend + 15m Entry`\n- المعيار: `7/10 مؤشرات مركبة`")

    while True:
        try:
            now = datetime.now()

            # التتبع كل 10 ثوانٍ
            for _ in range(6):
                for symbol in list(active_trades.keys()):
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        curr_p = ticker['last']
                        trade = active_trades[symbol]
                        if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                        
                        if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                            trade['trailing_active'] = True
                            send_telegram(f"⚡ *ملاحقة:* `{symbol}`")

                        reason = ""
                        if not trade['trailing_active'] and curr_p <= trade['sl']: reason = "🛑 SL"
                        elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 TP"

                        if reason:
                            pnl = (curr_p - trade['entry']) / trade['entry']
                            send_telegram(f"{reason}: `{symbol}` ({pnl*100:+.2f}%)")
                            del active_trades[symbol]
                    except: continue
                time.sleep(10)

            # فتح صفقات جديدة
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                
                for s in potential[:100]:
                    if s in active_trades: continue
                    if len(active_trades) >= MAX_TRADES: break
                        
                    change_24h = tickers[s]['percentage'] / 100
                    sig = analyze_multi_tf(s, change_24h)
                    
                    if sig and sig['ready']:
                        entry_p = sig['price']
                        active_trades[s] = {
                            'entry': entry_p, 'sl': entry_p * (1 - STOP_LOSS_PCT), 
                            'highest_p': entry_p, 'trailing_active': False, 
                            'start_dt': now, 'start_time': now.strftime("%H:%M:%S")
                        }
                        send_telegram(f"💎 *Entry ({sig['score']}/10)*\n🪙 `{s}` | 💵 `{entry_p}`\n🛑 SL: `{entry_p*0.97:.6f}`\n🧬 *Multi-TF Verified*")

            # تقرير الساعة
            if now >= last_open_report_1h + timedelta(hours=1):
                if active_trades:
                    report = "📂 *تقرير الصفقات (ساعة):*\n"
                    for s, d in active_trades.items():
                        cp = exchange.fetch_ticker(s)['last']
                        pnl = (cp - d['entry']) / d['entry'] * 100
                        report += f"🔹 `{s}` | `{pnl:+.2f}%` | ⏳ `{str(now - d['start_dt']).split('.')[0]}`\n"
                    send_telegram(report)
                last_open_report_1h = now

        except: time.sleep(15)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Multi-TF v11.6 | {len(active_trades)} Trades"
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
