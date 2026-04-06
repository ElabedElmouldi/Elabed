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

# --- 2. الإعدادات المالية وقائمة الاستبعاد الشاملة ---
MAX_TRADES = 20
TRADE_AMOUNT = 25
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.025
TRAILING_CALLBACK = 0.01
MAX_24H_CHANGE = 0.10

# [تعديل] القائمة السوداء الموسعة (عملات مستقرة، قيادية، ومرتبطة بأصول)
BLACKLIST = [
    # عملات قيادية ثقيلة (بطيئة الحركة)
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'DOT/USDT', 'LTC/USDT',
    
    # عملات مستقرة (Stablecoins) - تمت إضافة USD1 وجميع رفقائها
    'USDC/USDT', 'FDUSD/USDT', 'USDP/USDT', 'TUSD/USDT', 'DAI/USDT', 'EUR/USDT', 
    'USD1/USDT', 'USDE/USDT', 'PYUSD/USDT', 'USTC/USDT', 'BUSD/USDT', 'AEUR/USDT',
    'USDS/USDT', 'USDSB/USDT', 'EURI/USDT', 'USDT/DAI', 'USDT/USDC',
    
    # عملات مغلفة ومرتبطة بالذهب (Wrapped & Gold)
    'WBTC/USDT', 'WETH/USDT', 'PAXG/USDT', 'RETH/USDT', 'STETH/USDT'
]

VOL_MIN = 10000000 
VOL_MAX = 400000000 

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
last_open_report_1h = datetime.now()

def get_indicators(df):
    close = df['c']
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()
    return ema50, ema20, rsi, macd, signal

# --- 3. محرك التحليل (7/10 مع الشروط الإجبارية) ---
def analyze_v11_9(symbol, change_24h):
    if change_24h >= MAX_24H_CHANGE: return {'ready': False}
    
    try:
        # جلب البيانات
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
        df_1h = pd.DataFrame(bars_1h, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_1h, _, rsi_1h, _, _ = get_indicators(df_1h)

        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df_15m = pd.DataFrame(bars_15m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_15m, ema20_15m, rsi_15m, macd, macd_sig = get_indicators(df_15m)

        # الشرط الإجباري 1: الاتجاه صاعد على الساعة
        if df_1h['c'].iloc[-1] <= ema50_1h.iloc[-1]: return {'ready': False}
        
        # الشرط الإجباري 2: انفجار سيولة (أكبر بـ 1.5 مرة)
        vol_avg = df_15m['v'].iloc[-20:-1].mean()
        if df_15m['v'].iloc[-1] < vol_avg * 1.5: return {'ready': False}

        # نظام النقاط المساعدة (5/8)
        score = 0
        if rsi_1h.iloc[-1] > 50: score += 1
        if df_15m['c'].iloc[-1] > ema20_15m.iloc[-1]: score += 1
        if 48 < rsi_15m.iloc[-1] < 72: score += 1
        if macd.iloc[-1] > macd_sig.iloc[-1]: score += 1
        if ema20_15m.iloc[-1] > ema50_15m.iloc[-1]: score += 1
        if df_15m['c'].iloc[-1] > df_15m['o'].iloc[-1]: score += 1
        if rsi_15m.iloc[-1] > rsi_15m.iloc[-2]: score += 1
        if df_1h['c'].iloc[-1] > df_1h['o'].iloc[-1]: score += 1

        if score >= 5:
            return {'price': df_15m['c'].iloc[-1], 'score': score + 2, 'ready': True}
            
    except: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_open_report_1h
    send_telegram("🛡️ *v11.9 Ultimate Shield Active*\n- تم تحديث قائمة المستبعدات (25+ عملة)\n- حماية كاملة من العملات المستقرة والبطيئة.")

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
                
                for s in potential[:120]:
                    if s in active_trades: continue
                    if len(active_trades) >= MAX_TRADES: break
                        
                    change_24h = tickers[s]['percentage'] / 100
                    sig = analyze_v11_9(s, change_24h)
                    
                    if sig and sig['ready']:
                        entry_p = sig['price']
                        active_trades[s] = {
                            'entry': entry_p, 'sl': entry_p * (1 - STOP_LOSS_PCT), 
                            'highest_p': entry_p, 'trailing_active': False, 
                            'start_dt': now, 'start_time': now.strftime("%H:%M:%S")
                        }
                        send_telegram(
                            f"💎 *Entry Verified ({sig['score']}/10)*\n"
                            f"🪙 `{s}` | 💵 `{entry_p}`\n"
                            f"🛡️ استبعاد المستقرة: `نشط` ✅"
                        )

            # تقرير الساعة
            if now >= last_open_report_1h + timedelta(hours=1):
                if active_trades:
                    report = "📂 *حصاد الصفقات (ساعة):*\n"
                    for s, d in active_trades.items():
                        try:
                            cp = exchange.fetch_ticker(s)['last']
                            pnl = (cp - d['entry']) / d['entry'] * 100
                            report += f"🔹 `{s}` | `{pnl:+.2f}%` | ⏳ `{str(now - d['start_dt']).split('.')[0]}`\n"
                        except: continue
                    send_telegram(report)
                last_open_report_1h = now

        except: time.sleep(15)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Ultimate Shield v11.9 | Active"
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
