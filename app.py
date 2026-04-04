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
daily_history = [] # ذاكرة التقرير اليومي

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: pass

def get_btc_status(exchange):
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        return ((bars[1][4] - bars[0][1]) / bars[0][1]) * 100
    except: return 0

def send_hourly_status():
    """تقرير الساعة: متابعة الصفقات المفتوحة حالياً"""
    if not active_trades: return
    exchange = ccxt.binance()
    report = "⏳ **تقرير الصفقات المفتوحة (ساعي)**\n"
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
                       f"----------------------------\n")
        except: continue
    send_telegram(report)

def send_daily_summary():
    """تقرير 24 ساعة: حصاد الصفقات التي أغلقت اليوم"""
    if not daily_history:
        send_telegram("📅 **التقرير اليومي:** لم يتم إغلاق أي صفقات اليوم.")
        return
    
    wins = [t for t in daily_history if "هدف" in t['result']]
    losses = [t for t in daily_history if "وقف" in t['result']]
    
    report = "📅 **حصاد الصفقات (آخر 24 ساعة)**\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    for trade in daily_history:
        icon = "✅" if "هدف" in trade['result'] else "🛑"
        report += f"{icon} **{trade['symbol']}**: {trade['result']}\n"
    
    win_rate = (len(wins) / len(daily_history)) * 100
    report += (f"━━━━━━━━━━━━━━━━━━\n"
               f"📊 **الملخص:**\n"
               f"✅ ناجحة: {len(wins)} | 🛑 خاسرة: {len(losses)}\n"
               f"🎯 نسبة النجاح: `{win_rate:.1f}%`")
    
    send_telegram(report)
    daily_history.clear() # تصفير القائمة ليوم جديد

def check_market_logic():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        btc_change = get_btc_status(exchange)

        # تفعيل المعلق
        to_activate = []
        for symbol, data in pending_signals.items():
            if btc_change < -1.5: continue
            price = exchange.fetch_ticker(symbol)['last']
            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price, 'tp': price * 1.05, 'sl': price * 0.97,
                    'is_secured': False, 'max_peak': 0.0, 'max_drop': 0.0
                }
                send_telegram(f"📥 **دخول صفقة جديدة**: #{symbol.replace('/USDT','')}")
                to_activate.append(symbol)
        for s in to_activate: del pending_signals[s]

        # متابعة الأهداف
        to_remove = []
        for symbol, data in active_trades.items():
            price = exchange.fetch_ticker(symbol)['last']
            profit = ((price - data['entry_price']) / data['entry_price']) * 100
            if profit > data['max_peak']: data['max_peak'] = profit
            if profit < data['max_drop']: data['max_drop'] = profit

            if profit >= 3.0 and not data['is_secured']:
                data['sl'] = data['entry_price']; data['is_secured'] = True
                send_telegram(f"🛡️ **تم التأمين**: {symbol}")

            if price >= data['tp']:
                daily_history.append({'symbol': symbol, 'result': 'تحقيق هدف 5%'})
                send_telegram(f"🏁 **خروج بربح**: {symbol}")
                to_remove.append(symbol)
            elif price <= data['sl']:
                res = 'خسارة -3%' if not data['is_secured'] else 'خروج تعادل (تأمين)'
                daily_history.append({'symbol': symbol, 'result': res})
                send_telegram(f"🏁 **إغلاق بوقف**: {symbol}")
                to_remove.append(symbol)
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 5000000]
        sorted_s = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:150]

        for symbol in sorted_s:
            if symbol in active_trades or symbol in pending_signals: continue
            bars_30m = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=50)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=2)
            df = pd.DataFrame(bars_30m, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            pre_pump = ((bars_4h[1][4] - bars_4h[0][1]) / bars_4h[0][1]) * 100
            if pre_pump > 3.0: continue

            # حساب RSI
            delta = df['c'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]

            recent_high = df['h'].iloc[-11:-1].max()
            curr_p = df['c'].iloc[-1]
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            width = ((df['c'].rolling(20).std() * 4) / df['c'].rolling(20).mean() * 100).iloc[-1]
            
            # فلتر RSI الجديد (55-80)
            if curr_p >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.6) and width < 6.0 and 55 < rsi < 80:
                pending_signals[symbol] = {'low_limit': curr_p, 'high_limit': curr_p * 1.008}
                send_telegram(f"📡 **إشارة رصد**: #{symbol.replace('/USDT','')}\n📊 RSI: `{rsi:.1f}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=15)
scheduler.add_job(send_hourly_status, 'interval', hours=1)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=0) # تقرير يومي الساعة 11 ليلاً
scheduler.start()

@app.route('/')
def home(): return "Bot v7.9 - Hourly & Daily Reporting Active"

if __name__ == "__main__":
    send_telegram("🚀 **تم تشغيل v7.9 بنجاح**\nالآن ستصلك تقارير ساعية (للمفتوح) وتقارير يومية (للمغلق).")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
