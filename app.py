import os
import requests
import ccxt
import pandas as pd
import numpy as np
import time
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

# إعداد السجلات لمراقبة أداء البوت في Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
APP_URL = os.getenv("APP_URL")

# ذاكرة الصفقات النشطة والمنتهية
trades_history = []  
active_trades = {}   

EXCLUDED_COINS = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'DAI/USDT', 'FDUSD/USDT', 'BNB/USDT']

def send_telegram(message):
    """إرسال الرسائل لجميع المعرفات المحددة"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except Exception as e:
            logger.error(f"Telegram Error: {e}")

def check_active_trades(exchange):
    """متابعة الصفقات المفتوحة وإرسال تنبيه فوري عند ضرب الهدف أو الوقف"""
    symbols_to_remove = []
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            status = None
            detail = ""

            # فحص الأهداف (8% , 5% , 3%)
            if current_price >= data['tp3']:
                status = "✅ ربح كامل (Target 3)"
                detail = "وصل السعر للهدف الثالث (+8%) 🔥"
            elif current_price >= data['tp2']:
                status = "✅ ربح ممتاز (Target 2)"
                detail = "وصل السعر للهدف الثاني (+5%) 💰"
            elif current_price >= data['tp1']:
                status = "✅ ربح أولي (Target 1)"
                detail = "وصل السعر للهدف الأول (+3%) ✨"
            elif current_price <= data['sl']:
                status = "🛑 خسارة (Stop Loss)"
                detail = "ضرب السعر وقف الخسارة (-3%) 📉"
            
            if status:
                exit_time = datetime.now().strftime("%H:%M")
                exit_msg = (f"🏁 **إغلاق صفقة: {symbol.replace('/USDT', '')}**\n"
                            f"النتيجة: {status}\n"
                            f"تفاصيل: {detail}\n"
                            f"سعر الخروج: `{current_price:.4f}`\n"
                            f"وقت الدخول: {data['entry_time']} ➔ الخروج: {exit_time}")
                send_telegram(exit_msg)

                trades_history.append({
                    'coin': symbol.replace('/USDT', ''),
                    'entry_time': data['entry_time'],
                    'exit_time': exit_time,
                    'result': status
                })
                symbols_to_remove.append(symbol)
        except: continue
    
    for s in symbols_to_remove:
        del active_trades[s]

def scan_market():
    """البحث عن فرص دخول جديدة بناءً على الاختراق والسيولة"""
    logger.info("🕒 دورة فحص السوق بدأت...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_active_trades(exchange) # متابعة الصفقات المفتوحة أولاً

        tickers = exchange.fetch_tickers()
        # تصفية العملات (أكبر من 800 ألف دولار سيولة)
        symbols = [s for s in tickers if s.endswith('/USDT') and s not in EXCLUDED_COINS 
                   and (tickers[s].get('quoteVolume') or 0) > 800000]
        
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]

        for symbol in sorted_symbols:
            if symbol in active_trades: continue # تخطي إذا كانت الصفقة مفتوحة
            
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                recent_high = df['h'].iloc[-16:-1].max() # قمة آخر 3.5 ساعات
                current_price = df['c'].iloc[-1]
                
                # حساب المؤشرات
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(20).mean()
                
                # شروط الدخول (اختراق + سيولة 1.8x + انضغاط بولنجر)
                if current_price >= recent_high and df['v'].iloc[-1] > (df['Vol_MA'].iloc[-1] * 1.8) and df['Width'].iloc[-1] < 5.0:
                    entry_time = datetime.now().strftime("%H:%M")
                    
                    # حفظ بيانات الصفقة للأهداف
                    active_trades[symbol] = {
                        'entry_time': entry_time,
                        'tp1': current_price * 1.03,
                        'tp2': current_price * 1.05,
                        'tp3': current_price * 1.08,
                        'sl': current_price * 0.97
                    }

                    # 📢 إشعار الدخول الفوري
                    entry_msg = (f"🔔 **إشارة دخول صفقة جديدة!**\n"
                                 f"━━━━━━━━━━━━━━\n"
                                 f"🪙 العملة: #{symbol.replace('/USDT', '')}\n"
                                 f"📥 سعر الدخول: `{current_price:.4f}`\n"
                                 f"⏰ الوقت: {entry_time}\n\n"
                                 f"🎯 **الأهداف المقترحة:**\n"
                                 f"🟢 هدف 1 (3%): `{active_trades[symbol]['tp1']:.4f}`\n"
                                 f"🟢 هدف 2 (5%): `{active_trades[symbol]['tp2']:.4f}`\n"
                                 f"🟢 هدف 3 (8%): `{active_trades[symbol]['tp3']:.4f}`\n\n"
                                 f"🔴 **الوقف (-3%):** `{active_trades[symbol]['sl']:.4f}`")
                    
                    send_telegram(entry_msg)
                    logger.info(f"Signal Found: {symbol}")
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

def send_daily_report():
    """إرسال ملخص الصفقات في نهاية اليوم"""
    if not trades_history: return
    msg = "📊 **تقرير الصفقات اليومي المجمع**\n----------------------------\n"
    for t in trades_history:
        msg += f"🪙 {t['coin']} | {t['entry_time']} ➔ {t['exit_time']} | {t['result']}\n"
    send_telegram(msg)
    trades_history.clear()

# إعداد المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
# التقرير الساعة 22:00 بتوقيت السيرفر (منتصف الليل بتوقيت تونس)
scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
scheduler.start()

@app.route('/')
def home(): return "🚀 Fast Lane Bot v6.4 - Entry & Exit Alerts Active"

if __name__ == "__main__":
    # إرسال تنبيه عند بداية تشغيل السيرفر للتأكد من الاتصال
    send_telegram("✅ **تم تشغيل البوت بنجاح!**\nالرادار يراقب 300 عملة الآن وسيرسل إشعارات الدخول فوراً.")
    scan_market() # تشغيل أول فحص يدوياً عند البداية
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
