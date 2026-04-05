import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. إعدادات الاستراتيجية المتقدمة ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 500.0   # رأس المال المستهدف
PERCENT_PER_TRADE = 0.20 # 20% لكل صفقة (5 خانات)
MAX_TRADES = 5
TARGET_PROFIT = 1.04     # الهدف النهائي 4%
DYNAMIC_EXIT_RSI = 70    # خروج سريع إذا تشبع الشراء عند 3% ربح
SECURE_PROFIT_TRIGGER = 1.02 # تأمين الصفقة عند 2% ربح
STOP_LOSS = 0.98         # وقف خسارة 2%
TIME_EXIT_HOURS = 12     # إغلاق الصفقة آلياً بعد 12 ساعة لتدوير الرصيد

active_trades = []
daily_closed_trades = []

# --- 3. وظائف التحليل المتقدمة ---

def get_market_data():
    """جلب أفضل 250 عملة لضمان دوران السيولة"""
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT']
        for s, d in tickers.items():
            if '/USDT' in s and s not in exclude and d['quoteVolume'] > 5000000:
                gainers.append({'symbol': s, 'vol': d['quoteVolume'], 'change': d['percentage']})
        # ترتيب حسب الحجم لضمان سيولة الدخول والخروج
        gainers.sort(key=lambda x: x['vol'], reverse=True)
        return [item['symbol'] for item in gainers[:250]]
    except: return []

def get_indicators(symbol):
    try:
        time.sleep(0.1)
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # مؤشر RSI
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        df['ma20'] = df['c'].rolling(20).mean()
        
        # فلتر فوليوم: حجم الشمعة الأخيرة > متوسط آخر 10 شمعات
        df['vol_ma'] = df['v'].rolling(10).mean()
        
        return df.iloc[-1]
    except: return None

# --- 4. منطق التداول الذكي ---

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_1h = datetime.now()
    last_2h = datetime.now()
    last_daily = datetime.now().date()

    send_telegram("🚀 *تم تشغيل البوت المطور (نسخة الـ 500$)* \nالاستراتيجية: `دوران سريع + تأمين أرباح`")

    while True:
        try:
            now = datetime.now()

            # تقارير دورية
            if now.date() > last_daily:
                # (دالة التقرير اليومي بجدول كما في الكود السابق)
                last_daily = now.date()

            if now >= last_1h + timedelta(hours=1):
                send_telegram(f"📡 *نبض البوت:* يعمل.. الرصيد: `{VIRTUAL_BALANCE:.2f}$` | صفقات مفتوحة: `{len(active_trades)}`")
                last_1h = now

            # البحث عن فرص (مع فلتر الفوليوم)
            symbols = get_market_data()
            if len(active_trades) < MAX_TRADES:
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    data = get_indicators(symbol)
                    if data is not None:
                        # شروط دخول مطورة: RSI هادئ + سعر تحت المتوسط + انفجار فوليوم بسيط
                        if data['rsi'] <= 45 and data['c'] <= data['ma20'] and data['v'] > data['vol_ma']:
                            entry_amt = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                            new_trade = {
                                'symbol': symbol, 'entry_price': data['c'], 'cost': entry_amt,
                                'target': data['c'] * TARGET_PROFIT, 'stop': data['c'] * STOP_LOSS,
                                'open_time': now, 'is_secured': False
                            }
                            active_trades.append(new_trade)
                            VIRTUAL_BALANCE -= entry_amt
                            send_telegram(f"🔔 *دخول ذكي:* `{symbol}` \nالسعر: `{data['c']:.4f}` | الفوليوم: `متزايد ✅`")

            # مراقبة وإدارة الصفقات المفتوحة
            if active_trades:
                tickers = exchange.fetch_tickers()
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    pnl_pct = (p_now / t['entry_price'])
                    
                    # 1. خروج زمني بعد 12 ساعة لتدوير الرصيد
                    if now >= t['open_time'] + timedelta(hours=TIME_EXIT_HOURS):
                        VIRTUAL_BALANCE += t['cost'] * pnl_pct
                        send_telegram(f"⏱️ *خروج زمني:* `{t['symbol']}` لفتح مجال للسيولة.")
                        active_trades.remove(t)
                        continue

                    # 2. تأمين الصفقة (Break-even) عند ربح 2%
                    if pnl_pct >= SECURE_PROFIT_TRIGGER and not t['is_secured']:
                        t['stop'] = t['entry_price'] # رفع الوقف لسعر الدخول
                        t['is_secured'] = True
                        send_telegram(f"🛡️ *تأمين:* `{t['symbol']}` (تم رفع الوقف لسعر الدخول)")

                    # 3. جني ربح مرن (إذا وصل 3% والمؤشرات تشبعت)
                    data_live = get_indicators(t['symbol'])
                    if pnl_pct >= 1.03 and data_live['rsi'] >= DYNAMIC_EXIT_RSI:
                        profit = t['cost'] * (pnl_pct - 1)
                        VIRTUAL_BALANCE += (t['cost'] + profit)
                        send_telegram(f"⚡ *خروج سريع:* `{t['symbol']}` \nالربح: `{profit:+.2f}$` (دوران سريع للسيولة)")
                        active_trades.remove(t); continue

                    # 4. الأهداف الأساسية (البيع التلقائي)
                    if p_now >= t['target'] or p_now <= t['stop']:
                        is_win = p_now >= t['target']
                        profit = t['cost'] * (pnl_pct - 1)
                        VIRTUAL_BALANCE += (t['cost'] + profit)
                        
                        icon = "✨" if is_win else "🛑"
                        send_telegram(f"{icon} *إغلاق:* `{t['symbol']}` | `{profit:+.2f}$` \nالرصيد: `{VIRTUAL_BALANCE:.2f}$`")
                        
                        # إضافة للتقرير اليومي
                        daily_closed_trades.append({
                            'symbol': t['symbol'], 'entry': t['entry_price'], 'exit': p_now,
                            'profit_pct': (pnl_pct-1)*100, 'profit_usdt': profit,
                            'open_time': t['open_time'], 'close_time': now
                        })
                        active_trades.remove(t)

            time.sleep(40)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(20)

# --- 5. التشغيل ---
if __name__ == "__main__":
    app_thread = Thread(target=run_web_server)
    app_thread.daemon = True
    app_thread.start()
    run_trading_logic()
