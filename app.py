import os, requests, ccxt, time, json, logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام ---
DATA_FILE = "trading_v20_final.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- بيانات التليجرام (تأكد من صحتها) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# --- إعدادات الاستراتيجية ---
MAX_OPEN_TRADES = 5
ENTRY_RISK_PCT = 0.20
INITIAL_SL_PCT = 3.0
BE_TRIGGER_PCT = 3.0
TRAIL_TP_TRIGGER = 5.0
COOLDOWN_MINUTES = 60
MIN_VOLUME_LIMIT = 30_000_000

# القوائم السوداء والبيضاء
BLACKLIST = ['USDC', 'FDUSD', 'TUSD', 'PAXG', 'DAI', 'EUR', 'GBP', 'BUSD', 'UP', 'DOWN', 'BEAR', 'BULL']

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"balance": 100.0, "active_trades": {}, "daily_trades": [], "cooldowns": {}}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

db = load_db()
CURRENT_BALANCE = db["balance"]
active_trades = db["active_trades"]
cooldowns = db.get("cooldowns", {})

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك التحليل (Squeeze & Market) ---

def check_multiframe_squeeze(exchange, symbol):
    try:
        bars_15 = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=30)
        df15 = pd.DataFrame(bars_15, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        df15['ma'] = df15['c'].rolling(20).mean()
        df15['std'] = df15['c'].rolling(20).std()
        bandwidth = ((df15['std'] * 4) / df15['ma']).iloc[-1]
        return bandwidth < 0.03 # ضيق أقل من 3%
    except: return False

def is_market_safe(exchange):
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        sma50 = df['c'].rolling(50).mean().iloc[-1]
        return df['c'].iloc[-1] > sma50
    except: return True

# --- نظام إشعارات الإدارة (تأمين وخروج) ---

def check_trade_management():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(active_trades.items()):
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # 1. إشعار التأمين عند +3%
            if profit_pct >= BE_TRIGGER_PCT and not data.get('is_secured', False):
                data['sl'] = data['entry_price'] * 1.001 
                data['is_secured'] = True
                send_telegram(f"🛡️ **إشعار تأمين صفقة**\n━━━━━━━━━━━━━━\n🪙 العملة: `#{symbol}`\n📈 الربح الحالي: `+3.00%`\n✅ الإجراء: تم نقل الوقف لنقطة الدخول.\nℹ️ الحالة: **آمنة 100%**")

            # 2. الملاحقة الذكية عند +5%
            if profit_pct >= TRAIL_TP_TRIGGER:
                new_sl = price * 0.985
                if new_sl > data['sl']:
                    data['sl'] = new_sl
                    if not data.get('is_trailing', False):
                        data['is_trailing'] = True
                        send_telegram(f"🚀 **إشعار ملاحقة أرباح**\n━━━━━━━━━━━━━━\n🪙 العملة: `#{symbol}`\n🔥 النتيجة: تجاوزت `+5.00%`\n🎯 الحالة: البوت يطارد القمة الآن.")

            # 3. إشعار الخروج النهائي
            if price <= data['sl']:
                execute_final_exit(symbol, data, price)
                to_remove.append(symbol)

        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Mgmt Error: {e}")

def execute_final_exit(symbol, data, exit_price):
    global CURRENT_BALANCE
    exit_time = datetime.now()
    entry_time = datetime.strptime(data['entry_time'], "%Y-%m-%d %H:%M")
    duration_str = str(exit_time - entry_time).split('.')[0]
    
    final_pct = ((exit_price - data['entry_price']) / data['entry_price']) * 100
    profit_usd = data['invested_amount'] * (final_pct / 100)
    
    # تحديث السجل
    cooldowns[symbol] = (datetime.now() + timedelta(minutes=COOLDOWN_MINUTES)).timestamp()
    db["daily_trades"].append({"symbol": symbol, "pct": round(final_pct, 2), "usd": round(profit_usd, 2), "duration": duration_str})
    
    CURRENT_BALANCE += (data['invested_amount'] + profit_usd)
    db["balance"] = CURRENT_BALANCE
    db["cooldowns"] = cooldowns
    save_db(db)

    # إشعار الخروج التفصيلي
    icon = "💎" if final_pct > 0 else "🛑"
    status = "ربح" if final_pct > 0 else "خسارة/تعادل"
    send_telegram(f"{icon} **إشعار إغلاق صفقة**\n━━━━━━━━━━━━━━\n"
                  f"🪙 العملة: `#{symbol}`\n"
                  f"📊 النتيجة: `{final_pct:+.2f}%` (${profit_usd:+.2f})\n"
                  f"⏱️ المدة: `{duration_str}`\n"
                  f"🏁 الحالة: `{status}`\n"
                  f"🏦 الرصيد الجديد: `${CURRENT_BALANCE:.2f}`")

# --- رادار الدخول (إشعارات الدخول) ---

def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not is_market_safe(exchange): return
        check_trade_management()
        
        tickers = exchange.fetch_tickers()
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and s.split('/')[0] not in BLACKLIST and d.get('quoteVolume', 0) > MIN_VOLUME_LIMIT]
        
        for symbol in sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:60]:
            if symbol in active_trades or len(active_trades) >= MAX_OPEN_TRADES: continue
            if symbol in cooldowns and time.time() < cooldowns[symbol]: continue
            if not check_multiframe_squeeze(exchange, symbol): continue
            
            time.sleep(0.05)
            bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['ma'] = df['c'].rolling(10).mean(); df['std'] = df['c'].rolling(10).std()
            df['upper'] = df['ma'] + (df['std'] * 2)
            
            # RSI
            delta = df['c'].diff(); g = (delta.where(delta > 0, 0)).rolling(14).mean(); l = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
            
            last = df.iloc[-1]; avg_vol = df['v'].rolling(10).mean().iloc[-2]
            
            if last['c'] > last['upper'] and last['v'] > avg_vol * 1.8 and 50 < rsi < 70:
                trade_size = CURRENT_BALANCE * ENTRY_RISK_PCT
                active_trades[symbol] = {
                    'entry_price': last['c'], 'invested_amount': trade_size,
                    'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'sl': last['c'] * 0.97, 'is_secured': False
                }
                save_db(db)
                # إشعار الدخول الفوري
                send_telegram(f"⚡ **إشعار دخول صفقة**\n━━━━━━━━━━━━━━\n"
                              f"🪙 العملة: `#{symbol}`\n"
                              f"📥 السعر: `{last['c']}`\n"
                              f"📈 RSI: `{rsi:.1f}`\n"
                              f"💰 القيمة: `${trade_size:.2f}`\n"
                              f"🔍 الفلتر: `Squeeze 15m Confirmed`")
    except: pass

# --- التقارير (ساعي ويومي) ---

def send_hourly_report():
    now = datetime.now().strftime("%H:%M")
    msg = f"🕒 **ملخص ساعة ({now})**\n━━━━━━━━━━━━━━\n🏦 الرصيد: `${CURRENT_BALANCE:.2f}`\n📦 الصفقات: `{len(active_trades)}/{MAX_OPEN_TRADES}`"
    send_telegram(msg)

def send_daily_summary():
    if not db["daily_trades"]: return
    msg = "📅 **التقرير الختامي لليوم**\n━━━━━━━━━━━━━━\n"
    total_usd = sum([t['usd'] for t in db['daily_trades']])
    for t in db['daily_trades']:
        msg += f"• `{t['symbol']}` | `{t['pct']}%` | `${t['usd']:+.2f}`\n"
    msg += f"━━━━━━━━━━━━━━\n💰 صافي الأرباح: `${total_usd:+.2f}`\n🏦 الرصيد النهائي: `${CURRENT_BALANCE:.2f}`"
    send_telegram(msg)
    db["daily_trades"] = []; save_db(db)

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=1)
scheduler.add_job(send_hourly_report, 'interval', hours=1)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=59)
scheduler.start()

@app.route('/')
def home(): return f"v20.0 Notifications Active - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram("🦾 **تم تشغيل نظام التداول v20.0**\nالإشعارات الفورية والتقارير مفعلة بالكامل.")
    app.run(host='0.0.0.0', port=10000)
