import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def get_btc_status(exchange):
    """فلتر البيتكوين: التأكد من أن السوق ليس في حالة انهيار"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        last_close = bars[-1][4]
        prev_close = bars[-2][4]
        change = ((last_close - prev_close) / prev_close) * 100
        # إذا هبط البيتكوين أكثر من 1.5% في ساعة، السوق خطر
        return change > -1.5
    except: return True

def calculate_stoch_rsi(df):
    """حساب مؤشر الاستوكاستك لتجنب الشراء في القمة"""
    rsi = df['RSI']
    low_rsi = rsi.rolling(14).min()
    high_rsi = rsi.rolling(14).max()
    stoch_rsi = (rsi - low_rsi) / (high_rsi - low_rsi + 1e-9)
    return stoch_rsi.rolling(3).mean() * 100

def scan_market():
    print("🚀 جاري الفحص العميق للسوق (الإصدار الاحترافي)...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        
        # 1. صمام أمان البيتكوين
        if not get_btc_status(exchange):
            print("⚠️ تحذير: البيتكوين يهبط بقوة، تم تعليق الإشارات مؤقتاً.")
            return

        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 2000000]
        top_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]

        for symbol in top_symbols:
            # 2. فلتر الاتجاه (4 ساعات)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
            df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            ema_100 = df_4h['c'].ewm(span=100, adjust=False).mean().iloc[-1]
            if df_4h['c'].iloc[-1] < ema_100: continue

            # 3. فحص فريم 15 دقيقة
            bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars_15m, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب المؤشرات
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
            df['Vol_MA'] = df['v'].rolling(10).mean() # متوسط سيولة آخر 10 شمعات
            
            delta = df['c'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
            df['Stoch_K'] = calculate_stoch_rsi(df)

            last = df.iloc[-1]
            
            # --- الشروط المدمجة العالية الدقة ---
            is_squeezed = last['Width'] < 1.8 # انضغاط شديد
            is_momentum = 51 <= last['RSI'] <= 65 # زخم مثالي
            is_volume_surge = last['v'] > (last['Vol_MA'] * 2.0) # انفجار سيولة ضعف المتوسط
            is_not_overbought = last['Stoch_K'] < 80 # ليس في منطقة تشبع شرائي خطرة

            if is_squeezed and is_momentum and is_volume_surge and is_not_overbought:
                price = last['c']
                msg = (f"💎 **فرصة ذهبية عالية الدقة**\n"
                       f"العملة: #{symbol.replace('/USDT', '')}\n"
                       f"الوضع: انفجار سيولة مدعوم بترند صاعد\n\n"
                       f"📥 دخول: `{price:.4f}`\n"
                       f"🎯 هدف: `{price*1.06:.4f}`\n"
                       f"🛑 وقف: `{price*0.97:.4f}`\n\n"
                       f"⚠️ ملاحظة: تم فحص البيتكوين والاستوكاستك قبل الإرسال.")
                send_telegram(msg)
                
    except Exception as e: print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home(): return "<h1>Trading Bot v4.0 - All Systems Secure</h1>"

if __name__ == "__main__":
    send_telegram("🛡️ **تحديث أمان شامل:** تم تفعيل فلاتر البيتكوين، السيولة التراكمية، والاستوكاستك.")
    scan_market()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
