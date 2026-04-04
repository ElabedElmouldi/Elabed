import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

# إعداد السجلات لمراقبة أداء البوت
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# ذاكرة النظام اللحظية
pending_signals = {}
active_trades = {}

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: 
            pass

def get_btc_status(exchange):
    """فلتر حماية: يمنع دخول صفقات جديدة إذا كان البيتكوين ينهار"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[1][4] - bars[0][1]) / bars[0][1]) * 100
        return change
    except: return 0

def check_market_logic():
    """المحرك الرئيسي: تفعيل الصفقات، التأمين عند +3%، والخروج عند الهدف/الوقف"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        btc_change = get_btc_status(exchange)

        # 1. تفعيل الصفقات المعلقة (إشعار الدخول)
        to_activate = []
        for symbol, data in pending_signals.items():
            if btc_change < -1.5: continue # حماية من تقلبات البيتكوين الحادة
            
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'entry_time': datetime.now().strftime("%H:%M:%S"),
                    'tp': price * 1.05, # هدف 5%
                    'sl': price * 0.97, # وقف أصلي -3%
                    'is_secured': False, # حالة التأمين
                    'max_peak': 0.0,
                    'max_drop': 0.0
                }
                send_telegram(f"📥 **تم دخول صفقة جديدة**\n━━━━━━━━━━━━━━\n🪙 العملة: #{symbol.replace('/USDT','')}\n💵 سعر الدخول: `{price:.4f}`\n🎯 الهدف: 5% | 🛑 الوقف: -3%\n⏰ الوقت: `{active_trades[symbol]['entry_time']}`")
                to_activate.append(symbol)
        for s in to_activate: del pending_signals[s]

        # 2. متابعة الصفقات المفتوحة (التأمين والخروج)
        to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # تحديث القمم والقيعان للتقرير الساعي
            if profit_pct > data['max_peak']: data['max_peak'] = profit_pct
            if profit_pct < data['max_drop']: data['max_drop'] = profit_pct

            # نظام التأمين الذكي: عند ربح +3%، يتم نقل الوقف لسعر الدخول فورا
            if profit_pct >= 3.0 and not data['is_secured']:
                data['sl'] = data['entry_price']
                data['is_secured'] = True
                send_telegram(f"🛡️ **تأمين الصفقة (Break-even)**\n━━━━━━━━━━━━━━\n🪙 {symbol}\n✅ السعر حقق +3% ربح.\n🔒 تم نقل الوقف لنقطة الدخول (0%).")

            # التحقق من شروط الخروج
            if price >= data['tp']:
                send_telegram(f"🏁 **خروج (تحقيق الهدف الكامل 5%)**\n🪙 {symbol}\n💰 سعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
            elif price <= data['sl']:
                msg = "ضرب وقف الخسارة (-3%)" if not data['is_secured'] else "خروج آمن على سعر الدخول (0%)"
                send_telegram(f"🏁 **إغلاق الصفقة**\n⚠️ النتيجة: {msg}\n🪙 {symbol}\n📉 سعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def send_hourly_status():
    """التقرير الساعي المطور لكل الصفقات النشطة"""
    if not active_trades: return

    exchange = ccxt.binance()
    report = "📊 **تقرير متابعة الصفقات (30m)**\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            curr = ticker['last']
            diff = ((curr - data['entry_price']) / data['entry_price']) * 100
            report += (f"🪙 **{symbol.replace('/USDT','')}**\n"
                       f"📥 دخول: `{data['entry_price']:.4f}` | حالي: `{curr:.4f}` ({'+' if diff > 0 else ''}{diff:.2f}%)\n"
                       f"🚀 أعلى: `+{data['max_peak']:.2f}%` | 📉 أقل: `{data['max_drop']:.2f}%`\n"
                       f"🛡️ التأمين: {'✅ مفعل' if data['is_secured'] else '⏳ بانتظار 3%'}\n"
                       f"🎯 الهدف: `{data['tp']:.4f}`\n"
                       f"----------------------------\n")
        except: continue
    send_telegram(report)

def scan_for_signals():
    """البحث عن إشارات 'الانفجار السعري' بفلاتر السيولة والـ RSI الجديد"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic() # تحديث الصفقات الحالية أولا
        
        tickers = exchange.fetch_tickers()
        # فلتر السيولة العالية: استهداف العملات القوية (> 5M$)
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 5000000]
        sorted_s = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:150]

        for symbol in sorted_s:
            if symbol in active_trades or symbol in pending_signals: continue
            
            # تحليل فريم 30 دقيقة وفلترة بـ 4 ساعات
            bars_30m = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=50)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=2)
            
            df = pd.DataFrame(bars_30m, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # فلتر الصعود المسبق: استبعاد العملات التي صعدت > 3% في آخر 4 ساعات
            pre_pump = ((bars_4h[1][4] - bars_4h[0][1]) / bars_4h[0][1]) * 100
            if pre_pump > 3.0: continue

            # حساب RSI (نطاق 55-80 لاقتناص الزخم الحقيقي)
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]

            # شروط الاستراتيجية المطورة
            recent_high = df['h'].iloc[-11:-1].max() # قمة آخر 5 ساعات
            curr_p = df['c'].iloc[-1]
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            width = ((df['c'].rolling(20).std() * 4) / df['c'].rolling(20).mean() * 100).iloc[-1]
            
            # دخول الصفقة: اختراق + سيولة انفجارية + RSI في النطاق الذهبي
            if curr_p >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.6) and width < 6.0 and 55 < rsi < 80:
                pending_signals[symbol] = {'low_limit': curr_p, 'high_limit': curr_p * 1.008}
                send_telegram(f"📡 **إشارة رصد (سيولة + زخم)**\n━━━━━━━━━━━━━━\n🪙 العملة: #{symbol.replace('/USDT','')}\n📥 نطاق الدخول: `{curr_p:.4f}` - `{curr_p*1.008:.4f}`\n📊 RSI: `{rsi:.1f}`\n⏳ بانتظار ملامسة السعر للدخول...")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول الزمني (القلب النابض للبوت)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home(): return "Bot v7.8 - Professional Secure Scalper Active"

if __name__ == "__main__":
    send_telegram("🚀 **تم تشغيل نظام v7.8 المطور**\nالاستراتيجية: اختراق 30m مع تأمين آلي عند 3%.\nالفلاتر: BTC Shield + RSI (55-80) + Pre-Pump Filter.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
