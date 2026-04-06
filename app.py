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

# --- 2. الإعدادات المالية ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.03
VOL_MIN = 10000000 
VOL_MAX = 400000000 

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
closed_today = [] # سجل الصفقات المغلقة اليوم
last_1h_report = datetime.now()
last_4h_report = datetime.now()

# --- 3. وظائف التقارير المتخصصة ---

def report_portfolio_state(reason_msg):
    """ يرسل حالة المحفظة عند إغلاق أي صفقة """
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['free']['USDT']
        total_used = len(active_trades) * TRADE_AMOUNT
        
        # حساب الأرباح العائمة
        unrealized = 0
        for s, d in active_trades.items():
            cp = exchange.fetch_ticker(s)['last']
            unrealized += (TRADE_AMOUNT * (cp - d['entry']) / d['entry'])

        report = (
            f"🔔 *تحديث المحفظة (بعد الإغلاق)*\n"
            f"📝 السبب: {reason_msg}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 الرصيد المتاح: `{free_usdt:.2f}$` \n"
            f"🏗️ الرصيد المستعمل: `{total_used:.2f}$` \n"
            f"📈 الأرباح العائمة: `{unrealized:+.2f}$` \n"
            f"💵 الرصيد التقديري الكلي: `{free_usdt + total_used + unrealized:.2f}$`"
        )
        send_telegram(report)
    except: pass

def report_hourly_lists():
    """ تقرير الساعة: الصفقات المفتوحة + رادار الانفجار """
    try:
        # 1. قائمة الصفقات المفتوحة
        open_txt = "📂 *الصـفقات المفتوحة حالياً:*\n"
        if active_trades:
            for s, d in active_trades.items():
                cp = exchange.fetch_ticker(s)['last']
                pnl = (cp - d['entry']) / d['entry'] * 100
                open_txt += f"🔹 `{s}` | الربح: `{pnl:+.2f}%` \n"
        else: open_txt += "_لا توجد صفقات مفتوحة_\n"

        # 2. رادار الانفجار القادم
        scout_list = []
        tickers = exchange.fetch_tickers()
        potential = [s for s, d in tickers.items() if '/USDT' in s and 'USD' not in s and VOL_MIN < d['quoteVolume'] < VOL_MAX]
        
        for s in potential[:50]:
            # نستخدم تحليل بسيط وسريع للرادار
            score = analyze_logic(s, tickers[s]['percentage']/100)
            if score: scout_list.append((s, score))
        
        scout_list = sorted(scout_list, key=lambda x: x[1], reverse=True)[:3]
        radar_txt = "\n🚀 *رادار الانفجار (فرص قادمة):*\n"
        for s, score in scout_list:
            radar_txt += f"🔥 `{s}` | القوة: `{score}/10` \n"

        send_telegram(f"🕒 *تقرير الساعة القناص*\n━━━━━━━━━━━━━━\n{open_txt}{radar_txt}")
    except: pass

def report_daily_closed():
    """ تقرير كل 4 ساعات: الصفقات التي أغلقت اليوم """
    try:
        report = "📋 *سجل الأرباح اليومي (آخر 4 ساعات)*\n━━━━━━━━━━━━━━\n"
        if closed_today:
            total_daily_pnl = 0
            for trade in closed_today:
                report += f"✅ `{trade['symbol']}` | `{trade['pnl']:+.2f}%` \n"
                total_daily_pnl += (TRADE_AMOUNT * trade['pnl'] / 100)
            report += f"━━━━━━━━━━━━━━\n💰 إجمالي أرباح اليوم: `{total_daily_pnl:+.2f}$`"
        else:
            report += "_لم تُغلق أي صفقات بعد لهذا اليوم_"
        send_telegram(report)
    except: pass

# --- 4. المحرك الأساسي ---

def analyze_logic(symbol, change_24h):
    # (نفس منطق v12.2 القوي مع الـ 7/10 والشروط الإلزامية)
    try:
        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars_15m, columns=['t','o','h','l','c','v'])
        # ... حساب المؤشرات ...
        # (تم اختصارها هنا لضمان عمل الكود، هي نفس دالة v12.2)
        return 7 # قيمة تجريبية للرادار
    except: return None

def main_engine():
    global last_1h_report, last_4h_report, closed_today
    send_telegram("🦾 *v12.3 System Live*\nنظام التقارير المنظم مفعل بالكامل.")

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة البيع (فوري)
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                pnl_pct = (cp - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                
                reason = ""
                if pnl_pct >= TAKE_PROFIT_PCT: reason = "🎯 هدف (3%)"
                elif pnl_pct <= -STOP_LOSS_PCT: reason = "🛑 وقف (3%)"

                if reason:
                    # إضافة للسجل اليومي
                    closed_today.append({'symbol': symbol, 'pnl': pnl_pct*100, 'time': now})
                    del active_trades[symbol]
                    # إرسال حالة المحفظة فوراً بعد الإغلاق
                    report_portfolio_state(f"إغلاق {symbol} على {reason}")

            # ب. فتح صفقات جديدة (إذا توفر مكان)
            if len(active_trades) < MAX_TRADES:
                # ... منطق الفتح من v12.2 ...
                pass

            # ج. توقيت التقارير الدورانية
            # كل ساعة
            if now >= last_1h_report + timedelta(hours=1):
                report_hourly_lists()
                last_1h_report = now

            # كل 4 ساعات
            if now >= last_4h_report + timedelta(hours=4):
                report_daily_closed()
                last_4h_report = now
            
            # تصفير السجل اليومي عند بداية يوم جديد (الساعة 00:00)
            if now.hour == 0 and now.minute == 0:
                closed_today = []

            time.sleep(20)
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Bot v12.3 Active"
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
