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
pending_signals = {}
active_trades = {}

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: pass

def get_btc_status(exchange):
    """فحص حالة البيتكوين لحماية الصفقات البديلة"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        open_p = bars[0][1]
        curr_p = bars[1][4]
        change = ((curr_p - open_p) / open_p) * 100
        return change # يعيد نسبة التغير في آخر ساعة
    except: return 0

def check_market_logic():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        btc_change = get_btc_status(exchange)

        # 1. تفعيل الصفقات (إشعار الدخول)
        to_activate = []
        for symbol, data in pending_signals.items():
            if btc_change < -1.5: continue # تجنب الدخول إذا انهار البيتكوين
            
            price = exchange.fetch_ticker(symbol)['last']
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'entry_time': datetime.now().strftime("%H:%M"),
                    'tp': price * 1.05,
                    'sl': price * 0.97,
                    'is_secured': False, # لم يتم التأمين بعد
                    'max_peak': 0.0,
                    'max_drop': 0.0
                }
                send_telegram(f"📥 **إشعار دخول صفقة**\n━━━━━━━━━━━━━━\n🪙 العملة: #{symbol.replace('/USDT','')}\n💵 سعر الدخول: `{price:.4f}`\n🎯 الهدف: 5% | 🛑 الوقف: -3%")
                to_activate.append(symbol)
        for s in to_activate: del pending_signals[s]

        # 2. متابعة الصفقات (التأمين والخروج)
        to_remove = []
        for symbol, data in active_trades.items():
            price = exchange.fetch_ticker(symbol)['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            if profit_pct > data['max_peak']: data['max_peak'] = profit_pct
            if profit_pct < data['max_drop']: data['max_drop'] = profit_pct

            # نظام التأمين عند ربح 3%
            if profit_pct >= 3.0 and not data['is_secured']:
                data['sl'] = data['entry_price'] # نقل الوقف لسعر الدخول
                data['is_secured'] = True
                send_telegram(f"🛡️ **إشعار تأمين الصفقة**\n━━━━━━━━━━━━━━\n🪙 العملة: {symbol}\n✅ السعر وصل لـ +3% ربح.\n🔒 تم نقل وقف الخسارة إلى سعر الدخول (0%).")

            # الخروج عند الهدف أو الوقف
            if price >= data['tp']:
                send_telegram(f"🏁 **إشعار خروج (ربح)**\n━━━━━━━━━━━━━━\n✅ تم تحقيق الهدف الكامل 5%\n🪙 العملة: {symbol}\n💰 سعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
            elif price <= data['sl']:
                res = "خسارة -3%" if not data['is_secured'] else "خروج على سعر الدخول (تأمين)"
                send_telegram(f"🏁 **إشعار خروج (وقف)**\n━━━━━━━━━━━━━━\n⚠️ النتيجة: {res}\n🪙 العملة: {symbol}\n📉 سعر الخروج: `{price:.4f}`")
                to_remove.append(symbol)
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic()
        
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 1000000]
        sorted_s = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:200]

        for symbol in sorted_s:
            if symbol in active_trades or symbol in pending_signals: continue
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI (فلتر القوة النسبية)
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]

            # شروط الاستراتيجية
            recent_high = df['h'].iloc[-11:-1].max()
            curr_p = df['c'].iloc[-1]
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            width = ((df['c'].rolling(20).std() * 4) / df['c'].rolling(20).mean() * 100).iloc[-1]
            
            # دخول الصفقة: اختراق + سيولة + RSI غير متشبع
            if curr_p >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.6) and width < 6.0 and 50 < rsi < 75:
                pending_signals[symbol] = {'low_limit': curr_p, 'high_limit': curr_p * 1.008}
                send_telegram(f"📡 **رصد إشارة قوية (30m)**\n🪙 #{symbol.replace('/USDT','')}\n📥 النطاق: `{curr_p:.4f}` - `{curr_p*1.008:.4f}`\n📊 RSI: `{rsi:.1f}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home(): return "Bot v7.5 - Secure Trading with 3% Insurance Active"

if __name__ == "__main__":
    send_telegram("🛡️ **تم تشغيل نظام التداول المؤمن v7.5**\nنظام الإشعارات الثلاثي (دخول، تأمين، خروج) نشط الآن.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
