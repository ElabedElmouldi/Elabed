


]import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام للمجموعة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

# أضف هنا أرقام الـ ID الخاصة بأصدقائك (تأكد أن كل صديق قد ضغط Start للبوت)
FRIENDS_IDS = [
    "5067771509", # الـ ID الخاص بك
    "2107567005", # الـ ID الصديق الأول



def send_to_all_friends(message):
    """إرسال التنبيه لكل الأصدقاء في القائمة"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")

def scan_mega_explosion():
    print("🔎 جاري فحص عملات 'النطاق الذهبي' للانفجار +10%...")
    try:
        exchange = ccxt.binance()
        # جلب بيانات جميع العملات مقابل USDT
        tickers = exchange.fetch_tickers()
        
        # تصفية العملات النشطة مقابل USDT
        symbols = [s for s in tickers if s.endswith('/USDT')]
        
        for symbol in symbols:
            ticker = tickers[symbol]
            daily_volume = ticker['quoteVolume']
            
            # --- فلتر السيولة المتوسطة (Market Cap Proxy) ---
            # نبحث عن عملات حجم تداولها اليومي بين 10 مليون و 250 مليون دولار
            # هذا النطاق هو الأسهل لتحقيق انفجار 10% بمجهود سيولة بسيط
            if 10_000_000 <= daily_volume <= 250_000_000:
                
                # جلب آخر 50 شمعة (فريم 15 دقيقة)
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # 1. حساب مؤشر ضغط البولنجر (Bollinger Squeeze)
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                # حساب العرض المئوي (Width)
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                
                # 2. حساب RSI (14)
                delta = df['c'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                df['RSI'] = 100 - (100 / (1 + rs))
                
                # جلب آخر قيم محسوبة
                last = df.iloc[-1]
                current_width = last['Width']
                current_rsi = last['RSI']
                current_price = last['c']

                # --- شروط الانفجار الصارمة ---
                # ضغط حاد جدا (Width < 1.2%) + قوة صاعدة (RSI 55-65)
                if not np.isnan(current_width) and current_width < 1.2 and 55 <= current_rsi <= 65:
                    
                    target_10 = current_price * 1.10  # هدف 10%
                    stop_loss = current_price * 0.96  # وقف 4% (لتحمل التذبذب)
                    
                    name = symbol.replace('/USDT', '')
                    msg = (
                        f"🌋 **إشارة انفجار بركاني (+10%)**\n"
                        f"العملة: #{name}\n\n"
                        f"📊 **حالة الضغط:** `{current_width:.2f}%` (انضغاط حاد)\n"
                        f"📈 **القوة (RSI):** `{current_rsi:.2f}`\n"
                        f"💰 **سيولة 24h:** `${daily_volume/1e6:.1f}M`\n\n"
                        f"📥 **دخول ماركت:** `{current_price:.4f}`\n"
                        f"🎯 **الهدف الرئيسي:** `{target_10:.4f}`\n"
                        f"🛑 **وقف الخسارة:** `{stop_loss:.4f}`\n\n"
                        f"⚠️ *ملاحظة: السيولة متوسطة، الحركة قد تكون سريعة جداً.*"
                    )
                    send_to_all_friends(msg)
                    
    except Exception as e:
        print(f"Error in Scanner: {e}")

# إعداد المجدول ليعمل كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_mega_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def index():
    return "<h1>Gold Range Explosion Radar is Running!</h1>"

if __name__ == "__main__":
    # رسالة عند بدء التشغيل للتأكد من الاتصال
    send_to_all_friends("🚀 **تم تشغيل رادار الانفجار السعري (+10%) بنجاح!**\nسأراقب الآن عملات النطاق الذهبي وأرسل التنبيهات للجميع.")
    
    # تشغيل فحص فوري عند الإقلاع
    scan_mega_explosion()
    
    # تشغيل السيرفر على منفذ رندر الافتراضي
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

 
   
