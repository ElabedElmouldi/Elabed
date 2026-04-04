import os, requests, ccxt, time, json, logging
import pandas as pd
from datetime import datetime
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- الإعدادات والاستقرار ---
DATA_FILE = "trading_v35_live.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
app = Flask(__name__)

TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                if "daily_ledger" not in data: data["daily_ledger"] = []
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
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- وظيفة إرسال تقرير الصفقات المفتوحة (كل ساعة) ---
def send_open_trades_report():
    if not db["active_trades"]:
        # اختيارياً: يمكنك تفعيل هذه السطر إذا أردت إشعاراً حتى لو لا توجد صفقات
        # send_telegram("🔍 **تقرير الساعة:** لا توجد صفقات مفتوحة حالياً.")
        return

    try:
        exchange = ccxt.binance()
        report_msg = "🕒 **تقرير الصفقات المفتوحة الآن**\n"
        report_msg += "━━━━━━━━━━━━━━━━━━\n"
        
        total_unrealized_pnl = 0
        
        for symbol, data in db["active_trades"].items():
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # حساب الربح/الخسارة الحالي
            pnl_pct = ((current_price - data['entry_price']) / data['entry_price']) * 100
            pnl_usd = data['invested_amount'] * (pnl_pct / 100)
            total_unrealized_pnl += pnl_usd
            
            res_icon = "🟢" if pnl_pct >= 0 else "🔴"
            
            report_msg += (f"{res_icon} **العملة:** `#{symbol}`\n"
                           f"⏰ **وقت الدخول:** `{data['entry_time']}`\n"
                           f"📥 **سعر الدخول:** `{data['entry_price']:.4f}`\n"
                           f"💹 **السعر الحالي:** `{current_price:.4f}`\n"
                           f"💵 **قيمة الصفقة:** `${data['invested_amount']:.2f}`\n"
                           f"📊 **النتيجة:** `{pnl_pct:+.2f}%` (`${pnl_usd:+.2f}`)\n"
                           f"------------------\n")
            
        report_msg += f"💰 **إجمالي الأرباح غير المحققة:** `${total_unrealized_pnl:+.2f}`\n"
        report_msg += f"🏦 **الرصيد المتاح:** `${db['current_balance']:.2f}`"
        
        send_telegram(report_msg)
    except Exception as e:
        logging.error(f"Open trades report error: {e}")

# --- محرك البحث وإدارة الصفقات (النسخ السابقة v33-v34) ---
def scan_markets():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if len(db["active_trades"]) >= 5: return
        tickers = exchange.fetch_tickers()
        # (منطق الفلاتر المتقدمة هنا...)
        # عند الدخول، يتم تخزين entry_time و entry_price كما في الكود السابق
    except: pass

def manage_trades():
    # (منطق مراقبة الأهداف والوقف وتحديث الـ daily_ledger هنا...)
    pass

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_markets, 'interval', minutes=1)
scheduler.add_job(manage_trades, 'interval', seconds=30)

# الوظيفة الجديدة: إرسال تقرير كل ساعة
scheduler.add_job(send_open_trades_report, 'interval', hours=1)

# التقرير اليومي النهائي (ملخص اليوم)
scheduler.add_job(lambda: send_daily_report(), 'cron', hour=23, minute=59)

scheduler.start()

@app.route('/')
def status(): return {"status": "Online", "active_trades_count": len(db['active_trades'])}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
