import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات v33.0 Pro Protection ---
DATA_FILE = "trading_v33_final.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
app = Flask(__name__)

TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الإدارة المالية
MAX_OPEN_TRADES = 5
RISK_PER_TRADE_PCT = 0.20 
RR_RATIO = 2.0
BE_TRIGGER_PCT = 3.0 # نقطة التأمين وجني الأرباح الجزئي

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

# --- وظيفة مراقبة البيتكوين (حماية السوق) ---
def is_market_safe(exchange):
    try:
        btc_ticker = exchange.fetch_ticker('BTC/USDT')
        change_24h = btc_ticker['percentage']
        # إذا هبط البيتكوين بقوة (مثلاً أكثر من 3% في 24 ساعة)، نعتبر السوق غير مستقر
        if change_24h < -3.0:
            return False
        return True
    except: return True

def get_indicators(df):
    if len(df) < 50: return None
    # المؤشرات الأساسية
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['ma20'] = df['c'].rolling(20).mean()
    df['std'] = df['c'].rolling(20).std()
    df['lower_band'] = df['ma20'] - (df['std'] * 2)
    
    # RSI & ATR
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    df['tr'] = pd.concat([df['h']-df['l'], abs(df['h']-df['c'].shift()), abs(df['l']-df['c'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    # فلتر حجم التداول (Volume Avg)
    df['vol_avg'] = df['v'].rolling(10).mean()
    return df

# --- رادار البحث المطور ---
def scan_markets():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 1. فحص أمان السوق (قاطع الدائرة)
        if not is_market_safe(exchange):
            return

        if len(db["active_trades"]) >= MAX_OPEN_TRADES: return
        tickers = exchange.fetch_tickers()
        
        # فلتر السيولة والارتفاع
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and 5.0 <= d.get('percentage', 0) <= 20.0 and d.get('quoteVolume', 0) > 10_000_000]

        for symbol in symbols:
            if symbol in db["active_trades"]: continue
            
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
            df4h = get_indicators(pd.DataFrame(bars_4h, columns=['ts','o','h','l','c','v']))
            if df4h is None or df4h['c'].iloc[-1] < df4h['ema50'].iloc[-1]: continue

            bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
            df5 = get_indicators(pd.DataFrame(bars_5m, columns=['ts','o','h','l','c','v']))
            if df5 is None: continue
            
            last = df5.iloc[-1]
            prev = df5.iloc[-2]

            # شرط الحجم (Volume Delta): حجم الشمعة الحالية > 1.5 * متوسط الحجم
            if last['v'] < (last['vol_avg'] * 1.5): continue

            # شرط الدخول الفني
            if (last['l'] <= last['lower_band']) and (prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']):
                entry_p = last['c']
                risk = last['atr'] * 1.5
                sl_p = entry_p - risk
                target_pct = max(3.0, (risk / entry_p * 100) * RR_RATIO)
                tp_p = entry_p * (1 + target_pct / 100)
                entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                trade_amt = db["current_balance"] * RISK_PER_TRADE_PCT
                db["current_balance"] -= trade_amt
                
                db["active_trades"][symbol] = {
                    'entry_price': entry_p, 'tp': tp_p, 'sl': sl_p, 
                    'invested_amount': trade_amt, 'entry_time': entry_time, 
                    'is_secured': False, 'partial_sold': False
                }
                
                with open(DATA_FILE, 'w') as f: json.dump(db, f)
                
                send_telegram(f"🔥 **دخول صفقة آمنة (v33)**\n━━━━━━━━━━━━━━\n"
                              f"🪙 **العملة:** `{symbol}`\n"
                              f"📥 **سعر الدخول:** `{entry_p:.4f}`\n"
                              f"💵 **القيمة:** `${trade_amt:.2f}`\n"
                              f"📊 **قوة الحجم:** `عالية ✅`\n"
                              f"🛑 **الوقف:** `{sl_p:.4f}`\n"
                              f"💰 **الهدف:** `{tp_p:.4f}`\n"
                              f"⏰ **الوقت:** `{entry_time}`")
    except: pass

# --- إدارة الصفقات (جني أرباح جزئي وتأمين) ---
def manage_trades():
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(db["active_trades"].items()):
            price = exchange.fetch_ticker(symbol)['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100

            # 1. جني أرباح جزئي (60%) وتأمين الباقي عند 3%
            if profit_pct >= BE_TRIGGER_PCT and not data.get('partial_sold', False):
                sold_amt = data['invested_amount'] * 0.60
                profit_usd = sold_amt * (profit_pct / 100)
                db["current_balance"] += (sold_amt + profit_usd)
                data['invested_amount'] -= sold_amt
                data['sl'] = data['entry_price'] * 1.001
                data['partial_sold'] = True
                data['is_secured'] = True
                save_db(db)
                send_telegram(f"💰 **جني أرباح جزئي (60%) لـ {symbol}**\nتم تأمين الباقي عند سعر الدخول.")

            # 2. الخروج النهائي
            if price >= data['tp'] or price <= data['sl']:
                execute_final_exit(symbol, data, price)
                to_remove.append(symbol)
        for s in to_remove: del db["active_trades"][s]
        save_db(db)
    except: pass

def execute_final_exit(symbol, data, price):
    pct = ((price - data['entry_price']) / data['entry_price']) * 100
    profit_usd = data['invested_amount'] * (pct / 100)
    db["current_balance"] += (data['invested_amount'] + profit_usd)
    db["daily_trades"].append({"symbol": symbol, "pct": round(pct, 2), "usd": round(profit_usd, 2)})
    icon = "✅" if pct > 0 else "🛑"
    send_telegram(f"{icon} **خروج نهائي من {symbol}**\nالنتيجة: `{pct:+.2f}%`\n🏦 الرصيد: `${db['current_balance']:.2f}`")

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

# --- المجدول والسيرفر ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_markets, 'interval', minutes=1)
scheduler.add_job(manage_trades, 'interval', seconds=30)
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
