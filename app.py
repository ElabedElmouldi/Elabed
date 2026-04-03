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

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
APP_URL = os.getenv("APP_URL")

# ذاكرة الصفقات
trades_history = []  
active_trades = {}   

EXCLUDED_COINS = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'DAI/USDT', 'FDUSD/USDT', 'BNB/USDT']

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def check_active_trades(exchange):
    """متابعة الصفقات وإرسال تنبيه فور الخروج"""
    symbols_to_remove = []
    for symbol, data in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            status = None
            detail = ""

            # فحص الأهداف بالترتيب من الأعلى للأقل
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
                
                # إرسال تنبيه الخروج فوراً
                exit_msg = (f"🏁 **تحديث صفقة: {symbol.replace('/USDT', '')}**\n"
                            f"النتيجة: {status}\n"
                            f"تفاصيل: {detail}\n"
                            f"سعر الخروج: `{current_price:.4f}`\n"
                            f"وقت الدخول: {data['entry_time']} ➔ الخروج: {exit_time}")
                send_telegram(exit_msg)

                # إضافة للتقرير اليومي
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
    logger.info("🕒 دورة فحص ومتابعة بدأت...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_active_trades(exchange)

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s not in EXCLUDED_COINS 
                   and (tickers[s].get('quoteVolume') or 0) > 800000]
        
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:300]

        for symbol in sorted_symbols:
            if symbol in active_trades: continue
            
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                recent_high = df['h'].iloc[-16:-1].max()
                current_price = df['c'].iloc[-1]
                
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(20).mean()
                
                if current_price >= recent_high and df['v'].iloc[-1] > (df['Vol_MA'].iloc[-1] * 1.8) and df['Width'].iloc[-1] < 5.0:
                    entry_time = datetime.now().strftime("%H:%M")
                    active_trades[symbol] = {
                        'entry_time': entry_time,
                        'tp1': current_price * 1.03,
                        'tp2': current_price * 1.05,
                        'tp3': current_price * 1.08,
                        'sl': current_price * 0.97
                    }

                    msg = (f"🏇 **إشارة دخول قوية**\n"
                           f"العملة: #{symbol.replace('/USDT', '')}\n"
                           f"📥 دخول: `{current_price:.4f}`\n"
                           f"🎯 أهداف: 3% | 5% | 8%\n"
                           f"🛑 وقف: -3%")
                    send_telegram(msg)
            except: continue
    except Exception as e: logger.error(f"Scan Error: {e}")

def send_daily_report():
    if not trades_history: return
    msg = "📊 **تقرير الصفقات اليومي المجمع**\n----------------------------\n"
    for t in trades_history:
        msg += f"🪙 {t['coin']} | {t['entry_time']} ➔ {t['exit_time']} | {t['result']}\n"
    send_telegram(msg)
    trades_history.clear()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
# التقرير الساعة 23:00 بتوقيت تونس (22:00 بتوقيت السيرفر)
scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
scheduler.start()

@app.route('/')
def home(): return "🚀 Fast Lane Bot v6.2 - Instant Exit Notifications Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
