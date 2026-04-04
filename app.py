import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات v31.0 Multi-Timeframe ---
DATA_FILE = "trading_v31_mtf.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
app = Flask(__name__)

TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات المخاطر (رصيد 100$ + مصلحة مركبة)
MAX_OPEN_TRADES = 5
RISK_PER_TRADE_PCT = 0.20 
RR_RATIO = 2.0
BE_TRIGGER_PCT = 3.0

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"current_balance": 100.0, "active_trades": {}, "daily_trades": []}

db = load_db()

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك المؤشرات الفنية ---
def get_indicators(df):
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    # Bollinger
    df['ma20'] = df['c'].rolling(20).mean()
    df['std'] = df['c'].rolling(20).std()
    df['lower_band'] = df['ma20'] - (df['std'] * 2)
    # RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    # ATR
    df['tr'] = pd.concat([df['h']-df['l'], abs(df['h']-df['c'].shift()), abs(df['l']-df['c'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

# --- رادار البحث بالتأكيد الثلاثي ---
def scan_markets():
    try:
        if len(db["active_trades"]) >= MAX_OPEN_TRADES: return
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # فلتر Top Gainers (5-20%)
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and 5.0 <= d.get('percentage', 0) <= 20.0 and d.get('quoteVolume', 0) > 10_000_000]

        for symbol in symbols:
            if symbol in db["active_trades"]: continue
            
            # 1. فريم 4 ساعات: التأكد من الاتجاه العام (Above EMA 50)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=60)
            df4h = get_indicators(pd.DataFrame(bars_4h, columns=['ts','o','h','l','c','v']))
            if df4h['c'].iloc[-1] < df4h['ema50'].iloc[-1]: continue

            # 2. فريم ساعة: التأكد من الزخم (RSI > 50)
            bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
            df1h = get_indicators(pd.DataFrame(bars_1h, columns=['ts','o','h','l','c','v']))
            if df1h['rsi'].iloc[-1] < 50: continue

            # 3. فريم 15د أو 5د: نقطة الدخول (Lower BB + EMA Cross)
            bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=60)
            df5 = get_indicators(pd.DataFrame(bars_5m, columns=['ts','o','h','l','c','v']))
            last, prev = df5.iloc[-1], df5.iloc[-2]

            if (last['l'] <= last['lower_band']) and (prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']):
                # حساب مستويات ATR 1:2
                entry_p = last['c']
                risk = last['atr'] * 1.5
                sl_p = entry_p - risk
                target_pct = max(3.0, (risk / entry_p * 100) * RR_RATIO)
                tp_p = entry_p * (1 + target_pct / 100)

                # تنفيذ الدخول بـ 20% من الرصيد اللحظي
                trade_amt = db["current_balance"] * RISK_PER_TRADE_PCT
                db["current_balance"] -= trade_amt
                db["active_trades"][symbol] = {'entry_price': entry_p, 'tp': tp_p, 'sl': sl_p, 'invested_amount': trade_amt, 'is_secured': False}
                
                with open(DATA_FILE, 'w') as f: json.dump(db, f)
                send_telegram(f"🛡️ **تأكيد ثلاثي: {symbol}**\n━━━━━━━━━━━━━━\n"
                              f"🌍 اتجاه 4س: `إيجابي 💹`\n"
                              f"⚡ زخم ساعة: `RSI {df1h['rsi'].iloc[-1]:.1f}`\n"
                              f"📥 دخول 5د: `{entry_p}`\n"
                              f"💰 المبلغ: `${trade_amt:.2f}`")
    except: pass

# (وظائف manage_trades و execute_exit تظل كما هي في النسخة v30.0)

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_markets, 'interval', minutes=1)
# (بقية المهام المجدولة...)
scheduler.start()

if __name__ == "__main__":
    send_telegram("🦾 **v31.0 Activated (Multi-Timeframe)**\nTriple Filter Protection: Enabled")
    app.run(host='0.0.0.0', port=10000)
