import os
import requests
import ccxt
import pandas as pd
import numpy as np
import time
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import logging

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
APP_URL = os.getenv("APP_URL")

# ذاكرة الصفقات (تخزين مؤقت)
trades_history = []  # لتخزين الصفقات المنتهية للتقرير
active_trades = {}   # لمتابعة الصفقات المفتوحة

EXCLUDED_COINS = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'DAI/USDT', 'FDUSD/USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def scan_market():
    logger.info("🕒 فحص السوق ومتابعة الصفقات المفتوحة...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # 1. تحديث حالة الصفقات المفتوحة
        check_active_trades(exchange)

        # 2. البحث عن صفقات جديدة
        symbols = [s for s in tickers if s.endswith('/USDT') and s not in EXCLUDED_COINS 
                   and (tickers[s].get('quoteVolume') or 0) > 500000]
        
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]

        for symbol in sorted_symbols:
            if symbol in active_trades: continue # تخطي إذا كانت الصفقة مفتوحة بالفعل
            
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                recent_high = df['h'].iloc[-16:-1].max()
                current_price = df['c'].iloc[-1]
                
                # حساب المؤشرات
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(20).mean()
                
                # شرط الانفجار
                if current_price >= recent_high and df['v'].iloc[-1] > (df['Vol_MA'].iloc[-1] * 1.8) and df['Width'].iloc[-1] < 5.0:
                    
                    # تسجيل الصفقة في المتابعة النشطة
                    entry_time = datetime.now().strftime("%H:%M")
                    active_trades[symbol] = {
                        'entry_price': current_price,
                        'entry_time': entry_time,
                        'tp1': current_price * 1.03,
                        'tp2': current_price * 1.05,
                        'tp3': current_price * 1.08,
                        'sl': current_price * 0.97,
                        'status': 'Open'
                    }

                    msg = (f"🏇 **إشارة دخول جديدة**\n"
                           f"العملة: #{symbol.replace('/USDT', '')}\n"
                           f"📥 دخول: `{current_price:.4f}` الوقت: {entry_time}\n"
                           f"✅ أهداف: 3% | 5% | 8%\n"
                           f"🛑 وقف: -3%")
                    send_telegram(msg)
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

def check_active_trades(exchange):
    """متابعة الصفقات المفتوحة لتحديد وقت الانتهاء والنتيجة"""
    symbols_to_remove = []
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker['last']
            
            result = ""
            if last_price >= data['tp2']: # نعتبر الصفقة ناجحة عند الهدف الثاني
                result = "✅ ربح (Target Hit)"
            elif last_price <= data['sl']:
                result = "🛑 خسارة (Stop Loss)"
            
            if result:
                end_time = datetime.now().strftime("%H:%M")
                trades_history.append({
                    'coin': symbol.replace('/USDT', ''),
                    'entry': data['entry_time'],
                    'exit': end_time,
                    'result': result
                })
                symbols_to_remove.append(symbol)
        except: continue
    
    for s in symbols_to_remove: del active_trades[s]

def send_daily_report():
    """إرسال تقرير الصفقات كل 24 ساعة"""
    if not trades_history:
        send_telegram("📊 **التقرير اليومي:**\nلم يتم إغلاق أي صفقات اليوم.")
        return

    report = "📊 **تقرير الصفقات اليومي**\n"
    report += "----------------------------\n"
    for t in trades_history:
        report += f"🪙 {t['coin']} | 🕒 {t['entry']} -> {t['exit']} | {t['result']}\n"
    
    send_telegram(report)
    trades_history.clear() # تفريغ السجل لليوم الجديد

# المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.add_job(send_daily_report, 'cron', hour=23, minute=50) # يرسل التقرير قبل نهاية اليوم
scheduler.start()

@app.route('/')
def home(): return "<h1>Fast Lane Bot v6.0 - Reporting Active</h1>"

if __name__ == "__main__":
    send_telegram("🚀 تم تفعيل الرادار v6.0 مع نظام التقارير اليومية.")
    scan_market()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
