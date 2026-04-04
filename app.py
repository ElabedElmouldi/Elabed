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

# ذاكرة النظام
pending_signals = {}  # الصفقات التي ننتظر دخولها النطاق
active_trades = {}    # الصفقات المفتوحة حالياً
daily_history = []    # سجل الصفقات المغلقة لآخر 24 ساعة

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

def send_hourly_status():
    """تقرير الساعة: تفاصيل الصفقات المفتوحة مع أقصى صعود وهبوط"""
    if not active_trades: return

    exchange = ccxt.binance()
    report = "📊 **تقرير متابعة الصفقات النشطة (30m)**\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            curr_p = ticker['last']
            change = ((curr_p - data['entry_price']) / data['entry_price']) * 100
            
            report += (f"🪙 **{symbol.replace('/USDT','')}**\n"
                       f"⏰ وقت الدخول: `{data['entry_time']}`\n"
                       f"📥 سعر الدخول: `{data['entry_price']:.4f}`\n"
                       f"💰 السعر الحالي: `{curr_p:.4f}` ({'+' if change > 0 else ''}{change:.2f}%)\n"
                       f"🚀 أعلى صعود: `+{data['max_peak']:.2f}%`\n"
                       f"📉 أقل نزول: `{data['max_drop']:.2f}%`\n"
                       f"🎯 الهدف (5%): `{data['tp1']:.4f}`\n"
                       f"🛑 الوقف (-3%): `{data['sl']:.4f}`\n"
                       f"----------------------------\n")
        except: continue
    send_telegram(report)

def check_market_logic():
    """المحرك الرئيسي: تفعيل الصفقات ومتابعة الأهداف"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 1. مراقبة تفعيل الصفقات (عند وصول السعر للنطاق)
        to_activate = []
        for symbol, data in pending_signals.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'entry_time': datetime.now().strftime("%H:%M:%S"),
                    'max_peak': 0.0,
                    'max_drop': 0.0,
                    'tp1': price * 1.05, # هدف 5%
                    'sl': price * 0.97    # وقف -3%
                }
                send_telegram(f"✅ **لقد تم دخول صفقة جديدة**\n━━━━━━━━━━━━━━\n🪙 العملة: #{symbol.replace('/USDT','')}\n📥 سعر الدخول: `{price:.4f}`\n⏰ وقت الدخول: `{active_trades[symbol]['entry_time']}`\n🎯 الهدف: `{active_trades[symbol]['tp1']:.4f}`")
                to_activate.append(symbol)
        for s in to_activate: del pending_signals[s]

        # 2. تحديث الإحصائيات ومراقبة الخروج
        to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            change = ((price - data['entry_price']) / data['entry_price']) * 100
            
            if change > data['max_peak']: data['max_peak'] = change
            if change < data['max_drop']: data['max_drop'] = change

            if price >= data['tp1']:
                daily_history.append({'symbol': symbol, 'result': '✅ ربح 5%'})
                send_telegram(f"💰 **تم تحقيق الهدف (5%)!**\nالعملة: {symbol}\nسعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
            elif price <= data['sl']:
                daily_history.append({'symbol': symbol, 'result': '🛑 خسارة -3%'})
                send_telegram(f"🛑 **ضرب وقف الخسارة (-3%)**\nالعملة: {symbol}\nسعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def scan_for_signals():
    """البحث عن إشارات اختراق على فريم 30 دقيقة"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic() # تحديث الحالة قبل المسح الجديد
        
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
                # إرسال إشارة الرصد (نطاق الدخول)
                low_limit = curr_p
                high_limit = curr_p * 1.008 # نطاق 0.8%
                
                pending_signals[symbol] = {
                    'low_limit': low_limit,
                    'high_limit': high_limit
                }
                send_telegram(f"📡 **إشارة رصد (فريم 30 دقيقة)**\n━━━━━━━━━━━━━━\n🪙 العملة: #{symbol.replace('/USDT','')}\n📥 نطاق الدخول: `{low_limit:.4f}` - `{high_limit:.4f}`\n⏳ بانتظار تفعيل الدخول...")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home(): return "Bot v7.3 - Active with 30m Entry Zones"

if __name__ == "__main__":
    send_telegram("🛰️ **تم تفعيل نظام القناص v7.3**\nالهدف: 5% | الوقف: -3% | الفريم: 30 دقيقة.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
