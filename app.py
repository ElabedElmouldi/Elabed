import os
import requests
import ccxt
import pandas as pd
import numpy as np
import threading
import time
from flask import Flask
from datetime import datetime
from激 apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]
RENDER_URL = "https://your-app-name.onrender.com" # ⚠️ استبدله برابط تطبيقك في Render

# سجل الصفقات المؤقت (سيتم مسحه عند إعادة تشغيل السيرفر)
active_trades = []
daily_stats = {"wins": 0, "losses": 0, "total_profit": 0.0}

# --- وظائف التلغرام ---
def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# --- وظائف الحماية والتحليل ---
def get_btc_status(exchange):
    """منع التداول إذا كان البيتكوين في حالة هبوط حاد"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -1.5
    except: return True

def monitor_active_trades():
    """متابعة الصفقات المفتوحة وتحديث النتائج (فحص الأهداف والوقف)"""
    global active_trades, daily_stats
    if not active_trades: return

    exchange = ccxt.binance()
    remaining_trades = []

    for trade in active_trades:
        try:
            ticker = exchange.fetch_ticker(trade['symbol'])
            current_price = ticker['last']
            change = ((current_price - trade['entry']) / trade['entry']) * 100

            if change >= 6.0:
                daily_stats["wins"] += 1
                daily_stats["total_profit"] += 6.0
                send_telegram(f"✅ **ضرب الهدف!**\nالعملة: #{trade['symbol'].replace('/USDT','')}\nالربح: +6.0%\nالسعر: `{current_price}`")
            elif change <= -3.0:
                daily_stats["losses"] += 1
                daily_stats["total_profit"] -= 3.0
                send_telegram(f"❌ **ضرب الوقف!**\nالعملة: #{trade['symbol'].replace('/USDT','')}\nالخسارة: -3.0%\nالسعر: `{current_price}`")
            else:
                remaining_trades.append(trade)
        except:
            remaining_trades.append(trade)
    
    active_trades = remaining_trades

def send_daily_report():
    """ملخص الأداء اليومي"""
    report = (f"📊 **تقرير الحصاد اليومي**\n\n"
              f"✅ صفقات رابحة: {daily_stats['wins']}\n"
              f"❌ صفقات خاسرة: {daily_stats['losses']}\n"
              f"📈 صافي الربح التراكمي: {daily_stats['total_profit']:.2f}%")
    send_telegram(report)
    daily_stats.update({"wins": 0, "losses": 0, "total_profit": 0.0})

# --- الرادار الأساسي ---
def scan_market():
    print(f"🔍 فحص السوق: {datetime.now().strftime('%H:%M:%S')}")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): return

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 1000000]
        # التركيز على نطاق العملات السريعة (50-150)
        fast_lane = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[50:150]

        for symbol in fast_lane:
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                recent_high = df['h'].iloc[-20:-1].max()
                current_price = df['c'].iloc[-1]

                # حساب مؤشرات الانفجار
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(30).mean()

                last = df.iloc[-1]
                # شروط الدخول الصارمة
                if last['Width'] < 2.0 and current_price > recent_high and last['v'] > (last['Vol_MA'] * 3.0):
                    if not any(t['symbol'] == symbol for t in active_trades):
                        active_trades.append({'symbol': symbol, 'entry': current_price})
                        msg = (f"🏇 **إشارة خيل سريع (Spot)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"📥 دخول: `{current_price:.4f}`\n"
                               f"🎯 هدف (6%): `{current_price*1.06:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`")
                        send_telegram(msg)
            except: continue
    except Exception as e: print(f"Error: {e}")

# --- دالة التفعيل الذاتي (Keep Alive) ---
def keep_alive():
    """منع Render من النوم عن طريق مناداة الرابط كل 10 دقائق"""
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
            print("💓 نبض التفعيل الذاتي: البوت مستيقظ.")
        except:
            print("⚠️ تنبيه: فشل الاتصال الذاتي.")
        time.sleep(600) # 10 دقائق

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.add_job(monitor_active_trades, 'interval', minutes=5)
scheduler.add_job(send_daily_report, 'cron', hour=23, minute=55) # قبل نهاية اليوم بـ 5 دقائق
scheduler.start()

@app.route('/')
def home():
    return f"<h1>Trading Bot v6.0 is Running</h1><p>Active Trades: {len(active_trades)}</p>"

if __name__ == "__main__":
    # تشغيل خيط التفعيل الذاتي في الخلفية
    threading.Thread(target=keep_alive, daemon=True).start()
    
    send_telegram("🚀 **تم إطلاق البوت بنجاح!**\nنظام الرادار + المراقبة + التفعيل الذاتي قيد التشغيل.")
    scan_market()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
