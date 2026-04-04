import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# ذاكرة الصفقات
pending_signals = {} 
active_trades = {}

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: pass

def send_hourly_status():
    """تقرير الساعة: جرد كافة الصفقات المفتوحة حالياً"""
    if not active_trades:
        # اختياري: يمكنك تفعيل الرسالة أدناه إذا أردت تأكيداً حتى لو لا توجد صفقات
        # send_telegram("📝 **تقرير الساعة:** لا توجد صفقات مفتوحة حالياً.")
        return

    exchange = ccxt.binance()
    report = "📑 **تقرير الصفقات المفتوحة (تحديث ساعي)**\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            profit_pct = ((current_price - data['entry_price']) / data['entry_price']) * 100
            
            report += (f"🪙 **{symbol.replace('/USDT','')}**\n"
                       f"📥 دخول: `{data['entry_price']:.4f}`\n"
                       f"💰 حالي: `{current_price:.4f}` ({'+' if profit_pct > 0 else ''}{profit_pct:.2f}%)\n"
                       f"🎯 هدف (3%): `{data['tp1']:.4f}`\n"
                       f"🛑 وقف (-3%): `{data['sl']:.4f}`\n"
                       f"----------------------------\n")
        except:
            report += f"❌ تعذر جلب بيانات {symbol}\n"

    send_telegram(report)

def check_market_logic():
    """متابعة تفعيل الدخول ومراقبة الإغلاق"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 1. تفعيل الصفقات المنتظرة
        symbols_to_activate = []
        for symbol, data in pending_signals.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'tp1': price * 1.03,
                    'sl': price * 0.97
                }
                send_telegram(f"✅ **تم فتح الصفقة بنجاح**\n🪙 العملة: #{symbol.replace('/USDT','')}\n📥 سعر الدخول: `{price:.4f}`")
                symbols_to_activate.append(symbol)
        for s in symbols_to_activate: del pending_signals[s]

        # 2. إغلاق الصفقات النشطة (تلقائياً عند لمس الهدف أو الوقف)
        symbols_to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            if price >= data['tp1']:
                send_telegram(f"🏁 **إغلاق بربح (+3%):** {symbol}\nسعر الخروج: `{price:.4f}`")
                symbols_to_remove.append(symbol)
            elif price <= data['sl']:
                send_telegram(f"🏁 **إغلاق بوقف الخسارة (-3%):** {symbol}\nسعر الخروج: `{price:.4f}`")
                symbols_to_remove.append(symbol)
        for s in symbols_to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def scan_for_signals():
    """البحث عن إشارات جديدة"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic()

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 800000]
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]

        for symbol in sorted_symbols:
            if symbol in active_trades or symbol in pending_signals: continue
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            recent_high = df['h'].iloc[-16:-1].max()
            current_price = df['c'].iloc[-1]
            
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            width = ((df['c'].rolling(20).std() * 4) / df['c'].rolling(20).mean() * 100).iloc[-1]
            
            if current_price >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.8) and width < 5.0:
                pending_signals[symbol] = {
                    'low_limit': current_price,
                    'high_limit': current_price * 1.006
                }
                send_telegram(f"📡 **رصد إشارة:** #{symbol.replace('/USDT','')}\n📥 نطاق الدخول: `{current_price:.4f}` - `{current_price*1.006:.4f}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
# المهمة الجديدة: تقرير حالة الصفقات كل ساعة
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home(): return "Bot v6.9 - Hourly Reporting Active"

if __name__ == "__main__":
    send_telegram("🛰️ **تم تشغيل البوت v6.9**\nسأرسل لك تقريراً مفصلاً عن الصفقات المفتوحة كل ساعة.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
