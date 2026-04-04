import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام والاستقرار ---
DATA_FILE = "trading_db.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# بيانات التليجرام
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الاستراتيجية (إدارة رأس المال والمخاطر)
MAX_OPEN_TRADES = 5
RISK_PER_TRADE_PCT = 0.20   # الدخول بـ 20% من الرصيد الحالي
RR_RATIO = 2.0              # العائد للمخاطرة 1:2
BE_TRIGGER_PCT = 3.0        # تأمين عند 3% ربح
MIN_VOL_LIMIT = 10_000_000  # سيولة > 10 مليون

# --- وظائف قاعدة البيانات ---
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                if "current_balance" not in data: data["current_balance"] = 100.0
                return data
        except: pass
    return {"current_balance": 100.0, "active_trades": {}, "daily_trades": []}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

db = load_db()

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك المؤشرات الفنية (Multi-Timeframe Support) ---
def get_indicators(df):
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    # Bollinger Bands
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

# --- نظام إدارة وخروج الصفقات ---
def manage_trades():
    global db
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(db["active_trades"].items()):
            price = exchange.fetch_ticker(symbol)['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100

            # 1. تأمين الصفقة (Break-even)
            if profit_pct >= BE_TRIGGER_PCT and not data.get('is_secured', False):
                data['sl'] = data['entry_price'] * 1.001
                data['is_secured'] = True
                save_db(db)
                send_telegram(f"🛡️ **تأمين صفقة: {symbol}**\nالربح حُقق بنسبة `3%`. الوقف عند الدخول الآن.")

            # 2. الخروج النهائي (TP/SL)
            if price >= data['tp'] or price <= data['sl']:
                execute_exit(symbol, data, price)
                to_remove.append(symbol)
        
        for s in to_remove: del db["active_trades"][s]
        save_db(db)
    except Exception as e: logger.error(f"Error in Management: {e}")

def execute_exit(symbol, data, price):
    pct = ((price - data['entry_price']) / data['entry_price']) * 100
    profit_usd = data['invested_amount'] * (pct / 100)
    db["current_balance"] += (data['invested_amount'] + profit_usd)
    db["daily_trades"].append({"symbol": symbol, "pct": round(pct, 2), "usd": round(profit_usd, 2)})
    save_db(db)
    icon = "✅" if pct > 0 else "🛑"
    send_telegram(f"{icon} **خروج: {symbol}**\nالنتيجة: `{pct:+.2f}%` (`${profit_usd:+.2f}`)\n🏦 الرصيد: `${db['current_balance']:.2f}`")

# --- رادار البحث (التأكيد الثلاثي + ATR) ---
def scan_markets():
    global db
    try:
        if len(db["active_trades"]) >= MAX_OPEN_TRADES: return
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # فلتر البحث الأولي (Top Gainers)
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and 5.0 <= d.get('percentage', 0) <= 20.0 and d.get('quoteVolume', 0) > MIN_VOL_LIMIT]

        for symbol in symbols:
            if symbol in db["active_trades"]: continue
            
            # 1. تأكيد 4 ساعات (الاتجاه العام فوق EMA 50)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=60)
            df4h = get_indicators(pd.DataFrame(bars_4h, columns=['ts','o','h','l','c','v']))
            if df4h['c'].iloc[-1] < df4h['ema50'].iloc[-1]: continue

            # 2. تأكيد 1 ساعة (الزخم RSI > 50)
            bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
            df1h = get_indicators(pd.DataFrame(bars_1h, columns=['ts','o','h','l','c','v']))
            if df1h['rsi'].iloc[-1] < 50: continue

            # 3. فريم 5 دقائق (الدخول الفعلي: Bollinger + EMA Cross)
            bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=60)
            df5 = get_indicators(pd.DataFrame(bars_5m, columns=['ts','o','h','l','c','v']))
            last, prev = df5.iloc[-1], df5.iloc[-2]

            if (last['l'] <= last['lower_band']) and (prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']):
                # حساب مستويات ATR الرياضية 1:2
                entry_p = last['c']
                risk = last['atr'] * 1.5
                sl_p = entry_p - risk
                target_pct = max(3.0, (risk / entry_p * 100) * RR_RATIO)
                tp_p = entry_p * (1 + target_pct / 100)

                # تنفيذ الدخول (المصلحة المركبة)
                trade_amt = db["current_balance"] * RISK_PER_TRADE_PCT
                db["current_balance"] -= trade_amt
                db["active_trades"][symbol] = {'entry_price': entry_p, 'tp': tp_p, 'sl': sl_p, 'invested_amount': trade_amt, 'is_secured': False}
                save_db(db)
                
                send_telegram(f"⚡ **إشارة تأكيد ثلاثي: {symbol}**\n━━━━━━━━━━━━━━\n📥 دخول: `{entry_p}`\n🎯 الهدف: `+{target_pct:.1f}%`\n🛑 الوقف: `-{ (risk/entry_p*100):.1f}%`\n💰 المبلغ: `${trade_amt:.2f}`")
    except Exception as e: logger.error(f"Scanner Error: {e}")

# --- التقارير اليومية ---
def daily_summary():
    if not db["daily_trades"]: return
    total_usd = sum([t['usd'] for t in db['daily_trades']])
    msg = f"📅 **التقرير اليومي للأداء**\n━━━━━━━━━━━━━━\n"
    for t in db['daily_trades']: msg += f"• `{t['symbol']}`: `{t['pct']:+}%` (${t['usd']:+})\n"
    msg += f"━━━━━━━━━━━━━━\n💰 الربح: `${total_usd:+.2f}`\n🏦 الرصيد النهائي: `${db['current_balance']:.2f}`"
    send_telegram(msg)
    db["daily_trades"] = []; save_db(db)

# --- إعدادات السيرفر والاستمرارية ---
@app.route('/')
def status():
    return {
        "status": "Online",
        "balance": f"{db['current_balance']:.2f}",
        "active_trades": list(db['active_trades'].keys()),
        "last_update": datetime.now().strftime("%H:%M:%S")
    }

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_markets, 'interval', minutes=1)
scheduler.add_job(manage_trades, 'interval', seconds=30)
scheduler.add_job(daily_summary, 'cron', hour=23, minute=59)
scheduler.start()

if __name__ == "__main__":
    # استخدام البورت المخصص للسيرفر
    port = int(os.environ.get("PORT", 10000))
    send_telegram(f"🦾 **v32.0 Stable Activated**\nCompounding: On | Multi-TF: On")
    app.run(host='0.0.0.0', port=port)
