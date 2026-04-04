import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

# إعداد السجلات لمراقبة العمليات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- الإعدادات المالية والشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات المحفظة التراكمية
INITIAL_BALANCE = 100.0       
CURRENT_BALANCE = 100.0       
RISK_PER_TRADE_PCT = 20.0     # تقسيم المحفظة إلى 5 أجزاء (كل صفقة 20%)
MAX_OPEN_TRADES = 5           
LIQUIDITY_MIN_24H = 15000000  # الحد الأدنى للسيولة 15 مليون دولار

# ذاكرة النظام
active_trades = {}
daily_history = []

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except:
            pass

# --- محرك المؤشرات الفنية ---
def calculate_indicators(df):
    # 1. الاتجاه العام والزخم
    df['sma200'] = df['c'].rolling(window=200).mean()
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()

    # 2. البولينجر وضيق النطاق
    df['ma20'] = df['c'].rolling(window=20).mean()
    df['std'] = df['c'].rolling(window=20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']

    # 3. RSI و MACD
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    exp1 = df['c'].ewm(span=12, adjust=False).mean()
    exp2 = df['c'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    return df

# --- محرك الملاحقة اللصيقة (Trailing 1%) ---
def check_market_logic():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in active_trades.items():
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # حساب الربح اللحظي
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # منطق "الزحف اللصيق": الوقف دائماً تحت السعر الحالي بـ 1%
            potential_sl = price * 0.99 
            
            if potential_sl > data['sl']:
                old_sl_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                new_sl_pct = ((potential_sl - data['entry_price']) / data['entry_price']) * 100
                
                # تحديث الوقف وإرسال إشعار عند كل صعود صحيح بنسبة 1%
                if int(new_sl_pct) > int(old_sl_pct):
                    data['sl'] = potential_sl
                    send_telegram(f"📈 **زحف الوقف (+1%)**: {symbol}\nالربح المحجوز الآن: `{new_sl_pct:.1f}%` \nالسعر الحالي: `{price}`")
                else:
                    data['sl'] = potential_sl # تحديث صامت للحفاظ على المسافة

            # تنفيذ الخروج عند ضرب الوقف
            if price <= data['sl']:
                final_profit_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                profit_usd = data['invested_amount'] * (final_profit_pct / 100)
                
                CURRENT_BALANCE += profit_usd
                daily_history.append({'symbol': symbol, 'profit': round(final_profit_pct, 2), 'usd': profit_usd})
                
                icon = "💰" if final_profit_pct > 0 else "🛑"
                send_telegram(f"{icon} **إغلاق وحجز أرباح**: {symbol}\nالنتيجة: `{final_profit_pct:+.2f}%` (${profit_usd:+.2f})\n🏦 الرصيد الجديد: `${CURRENT_BALANCE:.2f}`")
                to_remove.append(symbol)
                
        for s in to_remove: del active_trades[s]
    except Exception as e:
        logger.error(f"Logic Error: {e}")

# --- رادار المسح واكتشاف الفرص ---
def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic() # تحديث الصفقات كل 60 ثانية
        
        tickers = exchange.fetch_tickers()
        # فلتر السيولة (15M+)
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > LIQUIDITY_MIN_24H]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:100]

        for symbol in symbols:
            if symbol in active_trades or len(active_trades) >= MAX_OPEN_TRADES: continue
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df = calculate_indicators(df)
            last = df.iloc[-1]
            
            # شروط الاستراتيجية (SMA 200 + Squeeze + Breakout)
            if last['c'] > last['sma200'] and last['bw'] < 0.03:
                if last['c'] > last['upper'] and last['ema9'] > last['ema21'] and 55 < last['rsi'] < 75:
                    
                    # حساب الحصة التراكمية
                    trade_size = CURRENT_BALANCE * (RISK_PER_TRADE_PCT / 100)
                    
                    active_trades[symbol] = {
                        'entry_price': last['c'],
                        'sl': last['c'] * 0.99, # الوقف الأولي تحت السعر بـ 1% فوراً
                        'invested_amount': trade_size,
                        'last_notified_sl_pct': -1.0
                    }
                    send_telegram(f"🎯 **اكتشاف انفجار سيولة**\n🪙 #{symbol.replace('/USDT','')}\n📏 الضيق: `{last['bw']*100:.1f}%` | RSI: `{last['rsi']:.1f}`\n💰 الحصة: `${trade_size:.2f}`\n🚀 نظام الملاحقة اللصيقة (1%) نشط!")
    except Exception as e:
        logger.error(f"Scan Error: {e}")

# --- التقارير الدورية ---
def send_hourly_report():
    if not active_trades:
        send_telegram("⏳ **تقرير الساعة**: لا صفقات مفتوحة. الرادار يبحث عن سيولة...")
        return
    
    msg = "📊 **حالة الصفقات المفتوحة**\n━━━━━━━━━━━━━━\n"
    for s, data in active_trades.items():
        try:
            curr_p = ccxt.binance().fetch_ticker(s)['last']
            p_pct = ((curr_p - data['entry_price']) / data['entry_price']) * 100
            msg += f"🪙 {s}: `{p_pct:+.2f}%` (الوقف الحالي: `{(data['sl']-data['entry_price'])/data['entry_price']*100:+.1f}%`)\n"
        except: pass
    
    growth = ((CURRENT_BALANCE - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    msg += f"━━━━━━━━━━━━━━\n📈 تطور المحفظة: `+{growth:.2f}%`"
    send_telegram(msg)

def send_daily_summary():
    if not daily_history: return
    total_usd = sum([d['usd'] for d in daily_history])
    growth_pct = ((CURRENT_BALANCE - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    
    report = (f"📅 **كشف الحساب اليومي**\n━━━━━━━━━━━━━━\n"
              f"✅ صفقات منتهية: `{len(daily_history)}` \n"
              f"💵 أرباح اليوم: `${total_usd:+.2f}` \n"
              f"🏦 رصيد المحفظة النهائي: `${CURRENT_BALANCE:.2f}` \n"
              f"📊 نسبة التطور الكلية: `+{growth_pct:.2f}%` \n"
              f"━━━━━━━━━━━━━━")
    send_telegram(report)
    daily_history.clear()

# --- تشغيل المجدول ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=1)
scheduler.add_job(send_hourly_report, 'interval', hours=1)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=55)
scheduler.start()

@app.route('/')
def home():
    return f"Bot v11.0 Running - Equity: ${CURRENT_BALANCE:.2f} - Open: {len(active_trades)}"

if __name__ == "__main__":
    send_telegram(f"🤖 **إطلاق النسخة v11.0 (Tight Trailing)**\n• نظام الزحف المئوي (1%) نشط.\n• فلتر SMA 200 + Liquidity فعال.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
