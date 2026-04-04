import os, requests, ccxt, time, json, logging
from datetime import datetime
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام والملفات ---
DATA_FILE = "royal_bot_v14_3.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الاستراتيجية الهجومية المركزة
MAX_OPEN_TRADES = 3      
ENTRY_RISK_PCT = 0.333   # دخول بـ 33.3% من المحفظة الحالية + الأرباح
BUFFER_PCT = 0.04        # ملاحقة السعر بمسافة 4%
BE_TRIGGER = 7.0         # تأمين عند 7% ربح
PARTIAL_TP_PCT = 15.0    # جني ربح جزئي عند 15%
MIN_VOLUME_LIMIT = 25_000_000 

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"balance": 100.0, "active_trades": {}, "daily_trades": []}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

db = load_db()
CURRENT_BALANCE = db["balance"]
active_trades = db["active_trades"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- إدارة الصفقات مع إشعارات تفصيلية ---
def check_trade_management():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(active_trades.items()):
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # 1. تأمين الربح عند +7%
            if profit_pct >= BE_TRIGGER and not data.get('is_secured', False):
                data['sl'] = data['entry_price'] * 1.01 
                data['is_secured'] = True
                send_telegram(f"🛡️ **تأمين صفقة: {symbol}**\n💰 الربح الحالي: `{profit_pct:.2f}%`\n✅ تم نقل الوقف لنقطة الدخول.")

            # 2. جني ربح جزئي عند +15%
            if profit_pct >= PARTIAL_TP_PCT and not data.get('is_partial_tp', False):
                realized_usd = (data['invested_amount'] * 0.5) * (profit_pct/100)
                tp_total = (data['invested_amount'] * 0.5) + realized_usd
                CURRENT_BALANCE += tp_total
                data['invested_amount'] *= 0.5 
                data['is_partial_tp'] = True
                send_telegram(f"💵 **جني أرباح جزئي: {symbol}**\n📈 النتيجة: `+{profit_pct:.2f}%` \n💰 ربح محقق: `${realized_usd:.2f}`\n🏦 الرصيد المتاح: `${CURRENT_BALANCE:.2f}`")

            # 3. ملاحقة 4%
            potential_sl = price * (1 - BUFFER_PCT)
            if potential_sl > data['sl']:
                data['sl'] = potential_sl

            # 4. إشعار الخروج النهائي التفصيلي
            if price <= data['sl']:
                exit_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                final_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                profit_loss_usd = data['invested_amount'] * (final_pct / 100)
                
                # تسجيل في السجل اليومي
                trade_log = {
                    "symbol": symbol, "entry_p": data['entry_price'], "exit_p": round(data['sl'], 5),
                    "amount": round(data['invested_amount'], 2), "pct": round(final_pct, 2),
                    "usd": round(profit_loss_usd, 2), "in_time": data['entry_time'], "out_time": exit_time
                }
                db["daily_trades"].append(trade_log)
                
                CURRENT_BALANCE += (data['invested_amount'] + profit_loss_usd)
                
                icon = "💎" if final_pct > 0 else "🛑"
                status = "ربح" if final_pct > 0 else "خسارة"
                send_telegram(f"{icon} **إغلاق صفقة نهائي**\n━━━━━━━━━━━━━━\n"
                              f"🪙 العملة: `#{symbol}`\n"
                              f"📥 سعر الدخول: `{data['entry_price']}`\n"
                              f"📤 سعر الخروج: `{data['sl']:.5f}`\n"
                              f"📊 النتيجة المئوية: `{final_pct:+.2f}%`\n"
                              f"💵 {status} محقق: `${profit_loss_usd:+.2f}`\n"
                              f"⏰ وقت الخروج: `{exit_time}`\n"
                              f"🏦 الرصيد الإجمالي: `${CURRENT_BALANCE:.2f}`")
                
                to_remove.append(symbol)
                save_db(db)

        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Mgmt Error: {e}")

# --- رادار الدخول مع إشعار تفصيلي ---
def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_trade_management()
        
        tickers = exchange.fetch_tickers()
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > MIN_VOLUME_LIMIT]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:100]

        for symbol in symbols:
            if symbol in active_trades or len(active_trades) >= MAX_OPEN_TRADES: continue
            time.sleep(0.1)

            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            avg_vol = df['v'].rolling(20).mean().iloc[-2]
            
            # حساب المؤشرات
            df['ma20'] = df['c'].rolling(20).mean(); df['std'] = df['c'].rolling(20).std()
            df['upper'] = df['ma20'] + (df['std'] * 2); df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']
            last = df.iloc[-1]

            if last['bw'] < 0.022 and last['c'] > last['upper'] and df['v'].iloc[-1] > avg_vol * 1.5:
                # حساب RSI
                delta = df['c'].diff(); g = (delta.where(delta > 0, 0)).rolling(14).mean(); l = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
                
                if 58 < rsi < 75:
                    entry_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                    trade_size = CURRENT_BALANCE * ENTRY_RISK_PCT
                    
                    active_trades[symbol] = {
                        'entry_price': last['c'], 'sl': last['c'] * (1 - BUFFER_PCT),
                        'invested_amount': trade_size, 'entry_time': entry_time,
                        'is_secured': False, 'is_partial_tp': False
                    }
                    save_db(db)
                    send_telegram(f"🚀 **فتح صفقة جديدة**\n━━━━━━━━━━━━━━\n"
                                  f"🪙 العملة: `#{symbol}`\n"
                                  f"📥 سعر الدخول: `{last['c']}`\n"
                                  f"💰 قيمة الاستثمار: `${trade_size:.2f}`\n"
                                  f"🛡️ وقف الخسارة الأولي: `{last['c']*(1-BUFFER_PCT):.5f}`\n"
                                  f"⏰ وقت الدخول: `{entry_time}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# --- التقرير اليومي الشامل (يرسل عند منتصف الليل) ---
def send_daily_summary():
    if not db["daily_trades"]:
        send_telegram("📅 **ملخص اليوم:** لم يتم إغلاق أي صفقات اليوم.")
        return
    
    msg = "📅 **كشف الحساب اليومي للعمليات**\n━━━━━━━━━━━━━━\n"
    total_day_usd = 0
    for t in db["daily_trades"]:
        msg += (f"🪙 `{t['symbol']}` | `{t['pct']}%` | `${t['usd']:+.2f}`\n"
                f"📥 دخل: `{t['entry_p']}` (${t['amount']})\n"
                f"📤 خرج: `{t['exit_p']}` | {t['out_time']}\n"
                f"------------------------\n")
        total_day_usd += t['usd']
    
    msg += f"📊 **صافي ربح اليوم:** `${total_day_usd:+.2f}`\n🏦 **الرصيد النهائي:** `${CURRENT_BALANCE:.2f}`"
    send_telegram(msg)
    db["daily_trades"] = []
    save_db(db)

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=2)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=59)
scheduler.start()

@app.route('/')
def home(): return f"v14.3 Running - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram(f"🏁 **تشغيل الرادار الاحترافي v14.3**\nتم تفعيل نظام التقارير والإشعارات التفصيلية.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=10000)
