import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
TARGET_ID = "5067771509" 

# قائمة الاستبعاد (العملات المستقرة والقيادية لتركيز البحث على الانفجارات)
EXCLUDED = ['BTC', 'ETH', 'USDT', 'USDC', 'BUSD', 'DAI', 'FDUSD', 'TUSD', 'WBTC']

def send_telegram_message(message):
    """إرسال التنبيهات إلى التلجرام مع معالجة الأخطاء"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Log: {response.json()}")
    except Exception as e:
        print(f"Connection Error: {e}")

def detect_price_explosion():
    """المحرك الرئيسي لاكتشاف الانفجار السعري بناءً على السلوك السعري والسيولة"""
    print("🧨 جاري فحص السوق بحثاً عن انفجارات سعرية...")
    try:
        # الاتصال بمنصة بينانس مع تفعيل حدود الطلبات
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers()
        
        # تصفية العملات البديلة ذات السيولة الجيدة (أكثر من 1.5 مليون دولار حجم تداول)
        symbols = [s for s in tickers if s.endswith('/USDT') and 
                   s.split('/')[0] not in EXCLUDED and 
                   tickers[s]['quoteVolume'] > 1500000]
        
        # اختيار أعلى 50 عملة من حيث السيولة
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]
        
        for symbol in sorted_symbols:
            # جلب آخر 100 شمعة (فريم 15 دقيقة)
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب Bollinger Bands (لقياس الانضغاط)
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            df['Upper'] = df['MA20'] + (df['STD'] * 2)
            df['Lower'] = df['MA20'] - (df['STD'] * 2)
            df['Width'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100
            
            # حساب RSI (لقياس القوة النسبية)
            delta = df['c'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # حساب متوسط السيولة (للتأكد من دخول فوليوم قوي)
            df['Vol_MA'] = df['v'].rolling(20).mean()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- شروط استراتيجية الانفجار السعري ---
            
            # 1. كان هناك انضغاط (Squeeze) في الشمعة السابقة (Width < 2.5)
            was_squeezed = prev['Width'] < 2.5
            
            # 2. اختراق السعر للحد العلوي للبولنجر (بداية الانطلاق)
            breakout_up = last['c'] > last['Upper']
            
            # 3. ارتفاع السيولة (أكبر من متوسط الـ 20 شمعة السابقة بـ 50%)
            volume_surge = last['v'] > (last['Vol_MA'] * 1.5)
            
            if was_squeezed and breakout_up and volume_surge:
                name = symbol.replace('/USDT', '')
                entry_price = last['c']
                
                # حساب الأهداف المطلوبة بدقة
                tp = entry_price * 1.05  # جني أرباح عند 5%
                sl = entry_price * 0.98  # وقف خسارة عند 2%
                
                msg = (
                    f"🧨 **إنذار: انفجار سعري مرتقب!**\n"
                    f"العملة: #{name}\n\n"
                    f"📥 **سعر الدخول:** `{entry_price:.4f}`\n"
                    f"🎯 **الهدف (5%+):** `{tp:.4f}`\n"
                    f"🛑 **الوقف (2%-):** `{sl:.4f}`\n\n"
                    f"📊 **بيانات الاختراق:**\n"
                    f"- RSI: {last['RSI']:.1f}\n"
                    f"- فوليوم: {((last['v']/last['Vol_MA'])):.1f}x ضعف المتوسط"
                )
                send_telegram_message(msg)
                
    except Exception as e:
        print(f"Error in Scanner: {e}")

# إعداد المجدول للعمل كل 15 دقيقة بشكل تلقائي
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(detect_price_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>Explosion Detector is Active!</h1>"

if __name__ == "__main__":
    # إرسال رسالة فورية عند تشغيل السيرفر للتأكد من وصول الإشعارات
    send_telegram_message("🚀 **تم تفعيل رادار الانفجار السعري!**\nجاري البحث عن فرص (هدف 5%، وقف 2%).")
    
    # تشغيل أول فحص يدوياً عند الإقلاع
    detect_price_explosion()
    
    # تحديد المنفذ الخاص بالاستضافة (Render/Oracle)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
