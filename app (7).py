import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def get_btc_status(exchange):
    """صمام أمان البيتكوين: يمنع الشراء إذا كان السوق ينهار"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = ((bars[-1][4] - bars[-2][4]) / bars[-2][4]) * 100
        return change > -1.5 # يسمح بالعمل إذا كان الهبوط أقل من 1.5%
    except: return True

def scan_market():
    print("🏇 جاري قنص العملات السريعة (الترتيب 50-150)...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        if not get_btc_status(exchange): return

        tickers = exchange.fetch_tickers()
        # تصفية العملات التي لديها سيولة معقولة للسبوت
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 1000000]
        
        # ترتيب العملات حسب السيولة واختيار النطاق السريع (من 50 إلى 150)
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        fast_lane_symbols = sorted_symbols[50:150] 

        for symbol in fast_lane_symbols:
            try:
                # 1. جلب بيانات 15 دقيقة للتحليل اللحظي
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # حساب الاختراق (Breakout): أعلى سعر في آخر 20 شمعة
                recent_high = df['h'].iloc[-20:-1].max()
                current_price = df['c'].iloc[-1]
                
                # 2. حساب المؤشرات (انضغاط + سيولة + RSI)
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                df['Vol_MA'] = df['v'].rolling(30).mean() # متوسط سيولة 7 ساعات
                
                delta = df['c'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

                last = df.iloc[-1]
                
                # --- شروط "الخيل السريع" ---
                is_squeezed = last['Width'] < 2.0  # السعر مضغوط وجاهز للانفجار
                is_breaking = current_price > recent_high # اختراق القمة المحلية
                has_huge_volume = last['v'] > (last['Vol_MA'] * 3.0) # سيولة 3 أضعاف المتوسط
                has_space = 52 <= last['RSI'] <= 64 # زخم قوي مع مساحة للصعود لـ 6%

                if is_squeezed and is_breaking and has_huge_volume and has_space:
                    # التأكد من الاتجاه الصاعد على فريم 4 ساعات (أمان إضافي للسبوت)
                    bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)
                    df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    ema_50 = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                    
                    if df_4h['c'].iloc[-1] > ema_50:
                        msg = (f"🏇 **إشارة عملة سريعة (Spot)**\n"
                               f"العملة: #{symbol.replace('/USDT', '')}\n"
                               f"الوضع: انفجار سيولة 3x + اختراق قمة\n\n"
                               f"📥 دخول: `{current_price:.4f}`\n"
                               f"🎯 هدف (6%): `{current_price*1.06:.4f}`\n"
                               f"🛑 وقف (3%): `{current_price*0.97:.4f}`\n\n"
                               f"⚡ العملة من الفئة السريعة، توقع حركة قوية!")
                        send_telegram(msg)
            except: continue
    except Exception as e: print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home(): return "<h1>Fast Lane Bot v5.0 - Active</h1>"

if __name__ == "__main__":
    send_telegram("🏇 **تم تفعيل رادار العملات السريعة!**\nالنطاق: 100 عملة (الترتيب 50-150).\nالهدف: قنص انفجارات الـ 6%.")
    scan_market()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
