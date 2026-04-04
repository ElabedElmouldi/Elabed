import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام v36.0 ---
DATA_FILE = "trading_db_final.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# بيانات التليجرام
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الاستراتيجية
MAX_OPEN_TRADES = 5
RISK_PER_TRADE_PCT = 0.20 
RR_RATIO = 2.0
BE_TRIGGER_PCT = 3.0

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                if "daily_ledger" not in data: data["daily_ledger"] = []
                if "current_balance" not in data: data["current_balance"] = 100.0
                return data
        except: pass
    return {"current_balance": 100.0, "active_trades": {}, "daily_ledger": []}

db = load_db()

def save_db():
    with open(DATA_FILE, 'w') as f:
        json.dump(db, f)

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

# --- وظائف المؤشرات والتحليل ---
def get_indicators(df):
    if len(df) < 50: return None
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ma20'] = df['c'].rolling(20).mean()
    df['std'] = df['c'].rolling(20).std()
    df['lower_band'] = df['ma20'] - (df['std'] * 2)
    df['tr'] = pd.concat([df['h']-df['l'], abs(df['h']-df['c'].shift()), abs(df['l']-df['c'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    df['vol_avg'] = df['v'].rolling(10).mean()
    return df

# --- التقرير الدوري (كل ساعة) ---
def send_hourly_status():
    if not db["active_trades"]: return
    try:
        exchange = ccxt.binance()
        msg = "🕒 **تقرير الحالة الساعة**\n━━━━━━━━━━━━━━\n"
        total_pnl = 0
        for symbol, data in db["active_trades"].items():
            price = exchange.fetch_ticker(symbol)['last']
            pnl_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            pnl_usd = data['invested_amount'] * (pnl_pct / 100)
            total_pnl += pnl_usd
            icon = "🟢" if pnl_pct >= 0 else "🔴"
            msg += f"{icon} `{symbol}`\n💰 السعر: `{price:.4f}`\n📊 الربح: `{pnl_pct:+.2f}%` (`${pnl_usd:+.2f}`)\n\n"
        msg += f"💵 إجمالي الربح العائم: `${total_pnl:+.2f}`"
        send_telegram(msg)
    except: pass

# --- التقرير اليومي النهائي ---
def send_daily_final_report():
    if not db["daily_ledger"]:
        send_telegram("📅 **تقرير اليوم:** لا توجد صفقات مغلقة اليوم.")
        return
    msg = "📊 **حصاد اليوم النهائي**\n━━━━━━━━━━━━━━\n"
    total_profit = 0
    for t in db["daily_ledger"]:
        icon = "✅" if t['usd'] > 0 else "🛑"
        msg += f"{icon} `{t['symbol']}` | `{t['pct']:+2f}%` | `${t['usd']:+.2f}`\n"
        total_profit += t['usd']
    msg += f"━━━━━━━━━━━━━━\n💰 صافي الربح: `${total_profit:+.2f}`\n🏦 الرصيد: `${db['current_balance']:.2f}`"
    send_telegram(msg)
    db["daily_ledger"] = []
    save_db()

# --- محرك البحث وإدارة الصفقات ---
def scan_markets():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if len(db["active_trades"]) >= MAX_OPEN_TRADES: return
        tickers = exchange.fetch_tickers()
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and 5.0 <= d.get('percentage', 0) <= 20.0 and d.get('quoteVolume', 0) > 10_000_000]

        for symbol in symbols:
            if symbol in db["active_trades"]: continue
            bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
            df = get_indicators(pd.DataFrame(bars_5m, columns=['ts','o','h','l','c','v']))
            if df is None: continue
            
            last, prev = df.iloc[-1], df.iloc[-2]
            if (last['v'] > last['vol_avg'] * 1.5) and (last['l'] <= last['lower_band']) and (prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']):
                entry_p = last['c']
                risk = last['atr'] * 1.5
                sl_p = entry_p - risk
                tp_p = entry_p * (1 + ((risk/entry_p)*2))
                
                trade_amt = db["current_balance"] * RISK_PER_TRADE_PCT
                db["current_balance"] -= trade_amt
                
                db["active_trades"][symbol] = {
                    'entry_price': entry_p, 'entry_time': datetime.now().strftime("%H:%M"),
                    'invested_amount': trade_amt, 'sl': sl_p, 'tp': tp_p, 'is_secured': False
                }
                save_db()
                send_telegram(f"🚀 **دخول جديد:** `{symbol}`\n📥 السعر: `{entry_p}` | 💵 القيمة: `${trade_amt:.2f}`")
    except: pass

def manage_trades():
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(db["active_trades"].items()):
            price = exchange.fetch_ticker(symbol)['last']
            pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            if pct >= BE_TRIGGER_PCT and not data['is_secured']:
                data['sl'] = data['entry_price'] * 1.001
                data['is_secured'] = True
                save_db()
                send_telegram(f"🛡️ **تأمين صفقة:** `{symbol}`")

            if price >= data['tp'] or price <= data['sl']:
                profit_usd = data['invested_amount'] * (pct / 100)
                db["current_balance"] += (data['invested_amount'] + profit_usd)
                db["daily_ledger"].append({"symbol": symbol, "pct": round(pct, 2), "usd": round(profit_usd, 2)})
                to_remove.append(symbol)
                send_telegram(f"🏁 **إغلاق:** `{symbol}` | نتيجة: `{pct:+.2f}%`")
        for s in to_remove: del db["active_trades"][s]
        save_db()
    except: pass

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_markets, 'interval', minutes=1)
scheduler.add_job(manage_trades, 'interval', seconds=30)
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.add_job(send_daily_final_report, 'cron', hour=23, minute=59)
scheduler.start()

@app.route('/')
def status(): return {"status": "Online", "balance": db['current_balance']}

if __name__ == "__main__":
    # --- رسالة التشغيل الفورية (هنا التعديل الذي طلبته) ---
    startup_msg = (f"🦾 **تم تشغيل البوت بنجاح v36.0**\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"🏦 الرصيد الحالي: `${db['current_balance']:.2f}`\n"
                   f"📊 نظام التقارير: `مفعل (كل ساعة)`\n"
                   f"🛡️ نظام الحماية: `نشط ✅`\n"
                   f"⏰ الوقت الحالي: `{datetime.now().strftime('%H:%M:%S')}`")
    send_telegram(startup_msg)
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
