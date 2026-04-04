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
daily_history = [] 

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

def send_hourly_status():
    """تقرير الساعة الشامل: يتضمن أعلى ارتفاع وأقل هبوط منذ الدخول"""
    if not active_trades:
        return 

    exchange = ccxt.binance()
    report = "📊 **تقرير متابعة الصفقات النشطة**\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            curr_price = ticker['last']
            
            # حساب النسبة المئوية الحالية
            current_change = ((curr_price - data['entry_price']) / data['entry_price']) * 100
            
            report += (f"🪙 **{symbol.replace('/USDT','')}**\n"
                       f"⏰ وقت الدخول: `{data['entry_time']}`\n"
                       f"📥 سعر الدخول: `{data['entry_price']:.4f}`\n"
                       f"💰 السعر الحالي: `{curr_price:.4f}` ({'+' if current_change > 0 else ''}{current_change:.2f}%)\n"
                       f"🚀 أعلى صعود وصل له: `+{data['max_peak']:.2f}%`\n"
                       f"📉 أقل نزول وصل له: `{data['max_drop']:.2f}%`\n"
                       f"🎯 الهدف (5%): `{data['tp1']:.4f}`\n"
                       f"🛑 الوقف (-3%): `{data['sl']:.4f}`\n"
                       f"----------------------------\n")
        except: continue
    
    send_telegram(report)

def check_market_logic():
    """تحديث القمم والقيعان اللحظية ومراقبة الأهداف"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 1. تفعيل المعلق
        to_activate = []
        for symbol, data in pending_signals.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'entry_time': datetime.now().strftime("%H:%M"),
                    'max_peak': 0.0,
                    'max_drop': 0.0,
                    'tp1': price * 1.05,
                    'sl': price * 0.97
                }
                send_telegram(f"✅ **تم تفعيل الصفقة بنجاح**\n🪙 العملة: #{symbol.replace('/USDT','')}\n📥 السعر: `{price:.4f}`")
                to_activate.append(symbol)
        for s in to_activate: del pending_signals[s]

        # 2. تحديث الإحصائيات (أعلى/أقل) ومراقبة الإغلاق
        to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # حساب التغير اللحظي لتحديث القمة والقاع
            change = ((price - data['entry_price']) / data['entry_price']) * 100
            if change > data['max_peak']: data['max_peak'] = change
            if change < data['max_drop']: data['max_drop'] = change

            if price >= data['tp1']:
                daily_history.append({'symbol': symbol, 'result': '✅ هدف 5%', 'entry': data['entry_price'], 'exit': price})
                send_telegram(f"💰 **تم تحقيق الهدف!** {symbol}")
                to_remove.append(symbol)
            elif price <= data['sl']:
                daily_history.append({'symbol': symbol, 'result': '🛑 وقف -3%', 'entry': data['entry_price'], 'exit': price})
                send_telegram(f"🛑 **خروج بوقف الخسارة** {symbol}")
                to_remove.append(symbol)
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic() # تحديث البيانات في كل دورة فحص (15د)
        
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 1000000]
        sorted_s = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]

        for symbol in sorted_s:
            if symbol in active_trades or symbol in pending_signals: continue
            bars = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            recent_high = df['h'].iloc[-11:-1].max()
            curr_p = df['c'].iloc[-1]
            
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            width = ((df['c'].rolling(20).std() * 4) / df['c'].rolling(20).mean() * 100).iloc[-1]
            
            if curr_p >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.5) and width < 6.0:
                pending_signals[symbol] = {'low_limit': curr_p, 'high_limit': curr_p * 1.008}
                send_telegram(f"📡 **إشارة مرصودة (30m):** #{symbol.replace('/USDT','')}\n📥 النطاق: `{curr_p:.4f}` - `{curr_p*1.008:.4f}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
# تقرير الساعة المطور
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home(): return "Bot v7.2 - Full Hourly Analytics Active"

if __name__ == "__main__":
    send_telegram("🛰️ **بدأت المراقبة بنظام v7.2**\nالتقرير الساعي سيتضمن الآن: وقت الدخول، القمة، والقاع منذ الدخول.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
