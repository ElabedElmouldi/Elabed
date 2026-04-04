import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

# إعداد السجلات لمراقبة أداء البوت اللحظي
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات الشخصية والقيود الأمنية (v8.6) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
MAX_OPEN_TRADES = 5  # سقف الصفقات لحماية المحفظة
MAX_SLIPPAGE = 0.008 # حماية الفجوة السعرية (0.8%)

# ذاكرة النظام المؤقتة
pending_signals = {}
active_trades = {}
daily_history = [] 

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: 
            pass

def get_btc_status(exchange):
    """فحص صحة السوق العام عبر البيتكوين"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        return ((bars[1][4] - bars[0][1]) / bars[0][1]) * 100
    except: return 0

def check_market_logic():
    """المحرك الذكي: فحص الصفقات وتحديث الوقف كل 60 ثانية"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        btc_change = get_btc_status(exchange)

        # 1. تفعيل الإشارات المعلقة (بسرعة دقيقة واحدة)
        to_activate = []
        for symbol, data in pending_signals.items():
            if len(active_trades) >= MAX_OPEN_TRADES: continue
            if btc_change < -1.5: continue
            
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # حماية الفجوة: إذا طار السعر بعيداً، نلغي الإشارة
            if price > (data['low_limit'] * (1 + MAX_SLIPPAGE)):
                to_activate.append(symbol)
                continue

            if data['low_limit'] <= price <= data['high_limit']:
                active_trades[symbol] = {
                    'entry_price': price,
                    'tp_trigger': price * 1.05, 
                    'sl': price * 0.97,
                    'is_secured': False,
                    'is_trailing': False,
                    'last_notified_sl_pct': 4.0 # مرجع تنبيهات المطاردة
                }
                send_telegram(f"📥 **تم دخول صفقة (تحديث دقيق)**\n━━━━━━━━━━━━━━\n🪙 #{symbol.replace('/USDT','')}\n💵 السعر: `{price:.4f}`\n🎯 الهدف الأولي: +5%")
                to_activate.append(symbol)
        
        for s in to_activate: 
            if s in pending_signals: del pending_signals[s]

        # 2. إدارة الصفقات النشطة والمطاردة (Trailing)
        to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            profit = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # أ- التأمين الآلي عند +3%
            if profit >= 3.0 and not data['is_secured'] and not data['is_trailing']:
                data['sl'] = data['entry_price']
                data['is_secured'] = True
                send_telegram(f"🛡️ **تأمين فوري (+3%)**\n🪙 {symbol}\n🔒 الوقف الآن عند نقطة الدخول (Risk Free).")

            # ب- بدء نظام المطاردة عند +5%
            if profit >= 5.0 and not data['is_trailing']:
                data['is_trailing'] = True
                data['sl'] = data['entry_price'] * 1.04 # حجز 4% كحد أدنى
                send_telegram(f"🚀 **انطلاق المطاردة (v8.6)**\n🪙 {symbol}\n✅ تجاوزنا 5%، الوقف يلاحق السعر الآن!")

            # ج- تحديث الوقف المتحرك والتنبيه عند كل 1% صعود إضافي
            if data['is_trailing']:
                potential_sl = price * 0.99 # الوقف يتبع السعر بفرق 1%
                current_sl_pct = ((potential_sl - data['entry_price']) / data['entry_price']) * 100
                
                # إرسال تنبيه فقط عند تحقيق قفزة 1% كاملة عن آخر تنبيه
                if current_sl_pct >= (data['last_notified_sl_pct'] + 1.0):
                    data['sl'] = potential_sl
                    data['last_notified_sl_pct'] = current_sl_pct
                    send_telegram(f"📈 **تحديث صعود (+1%)**\n🪙 {symbol}\n🚀 الربح: `{profit:.2f}%` | 🔒 الوقف المحمي: `{current_sl_pct:.1f}%`")
                elif potential_sl > data['sl']:
                    data['sl'] = potential_sl # تحديث صامت للوقف لضمان الدقة

            # د- تنفيذ الخروج اللحظي
            if price <= data['sl']:
                final_profit = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                daily_history.append({'symbol': symbol, 'profit': round(final_profit, 2)})
                
                icon = "💰" if final_profit > 0 else "🛑"
                send_telegram(f"{icon} **إغلاق الصفقة**\n━━━━━━━━━━━━━━\n🪙 {symbol}\n📉 سعر الخروج: `{price:.4f}`\n📊 النتيجة النهائية: `{final_profit:.2f}%`")
                to_remove.append(symbol)

        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

def send_daily_summary():
    """تقرير الحصاد اليومي المركب"""
    if not daily_history: return
    total_profit = sum([t['profit'] for t in daily_history])
    report = f"📅 **تقرير الأداء اليومي (v8.6)**\n━━━━━━━━━━━━━━\n"
    for t in daily_history:
        report += f"{'✅' if t['profit']>0 else '🛑'} {t['symbol']}: `{t['profit']}%`\n"
    report += f"━━━━━━━━━━━━━━\n📊 صافي نمو المحفظة: `+{total_profit:.2f}%`"
    send_telegram(report)
    daily_history.clear()

def scan_for_signals():
    """البحث عن اختراقات جديدة بفلاتر RSI والسيولة"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic() # الفحص اللحظي يأخذ الأولوية
        
        tickers = exchange.fetch_tickers()
        # استهداف العملات القوية فقط (Volume > 5M$)
        symbols = [s for s in tickers if s.endswith('/USDT') and (tickers[s].get('quoteVolume') or 0) > 5000000]
        sorted_s = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:150]

        for symbol in sorted_s:
            if symbol in active_trades or symbol in pending_signals: continue
            if len(active_trades) >= MAX_OPEN_TRADES: break
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب RSI (النطاق الذهبي 55-80)
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]

            recent_high = df['h'].iloc[-11:-1].max() # قمة آخر 5 ساعات
            curr_p = df['c'].iloc[-1]
            vol_ma = df['v'].rolling(20).mean().iloc[-1]
            
            # شرط الاختراق الانفجاري
            if curr_p >= recent_high and df['v'].iloc[-1] > (vol_ma * 1.6) and 55 < rsi < 80:
                pending_signals[symbol] = {'low_limit': curr_p, 'high_limit': curr_p * 1.008}
                send_telegram(f"📡 **رصد إشارة اختراق (v8.6)**\n━━━━━━━━━━━━━━\n🪙 #{symbol.replace('/USDT','')}\n📊 RSI: `{rsi:.1f}`\n⚡ الفحص القادم خلال 60 ثانية.")
    except Exception as e: logger.error(f"Scan Error: {e}")

# المجدول الزمني الفوري (كل دقيقة واحدة)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=1)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=50)
scheduler.start()

@app.route('/')
def home():
    return f"Bot v8.6 Live - Scanning: 1m - Active Trades: {len(active_trades)}/{MAX_OPEN_TRADES}"

if __name__ == "__main__":
    send_telegram("🚀 **إطلاق النسخة v8.6 (القناص الفوري)**\n━━━━━━━━━━━━━━\n• مسح السوق: كل 60 ثانية.\n• مطاردة الأرباح: نشطة.\n• سقف الصفقات: 5.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
