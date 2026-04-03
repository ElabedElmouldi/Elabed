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

def send_to_all(message):
    """إرسال رسالة لجميع المعرفات المضافة"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=5)
        except:
            pass

def heart_beat_job():
    """رسالة الحالة (كل ساعة) للتأكد من أن البوت يعمل"""
    print("💓 إرسال نبضة الحالة الدورية...")
    msg = "🟢 **تقرير الحالة:** البوت يعمل بشكل سليم ومستمر في مراقبة السوق."
    send_to_all(msg)

def get_btc_status(exchange):
    """تحليل اتجاه البيتكوين (فلتر الأمان)"""
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='15m', limit=20)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        sma = df['c'].mean()
        current_price = df['c'].iloc[-1]
        return "SAFE" if current_price >= sma else "RISKY"
    except:
        return "RISKY"

def scan_market():
    """فحص الانفجارات السعرية في العملات البديلة"""
    print("🔄 جاري فحص العملات البديلة...")
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        btc_status = get_btc_status(exchange)
        
        # إذا كان البيتكوين في حالة هبوط، لا نرسل توصيات
        if btc_status == "RISKY":
            return

        tickers = exchange.fetch_tickers()
        # تصفية العملات (أعلى 30 عملة سيولة مقابل USDT)
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in ['BTC', 'ETH', 'USDT']][:30]

        for symbol in symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب الانضغاط (Bollinger Width)
            df['MA20'] = df['c'].rolling(20).mean()
            df['STD'] = df['c'].rolling(20).std()
            width = ((df['MA20'] + (df['STD']*2)) - (df['MA20'] - (df['STD']*2))) / df['MA20'] * 100
            
            # حساب RSI
            diff = df['c'].diff()
            gain = diff.where(diff > 0, 0).rolling(14).mean()
            loss = -diff.where(diff < 0, 0).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))
            
            last_w = width.iloc[-1]
            last_rsi = rsi.iloc[-1]
            price = df['c'].iloc[-1]

            # شروط الانفجار (Width < 1.8 و RSI في منطقة الانطلاق)
            if last_w < 1.8 and 52 <= last_rsi <= 62:
                msg = (f"🧨 **إشارة انفجار سعري**\n"
                       f"العملة: #{symbol.replace('/USDT', '')}\n"
                       f"السوق: ✅ BTC آمن\n\n"
                       f"📥 دخول: `{price:.4f}`\n"
                       f"🎯 هدف (6%): `{price*1.06:.4f}`\n"
                       f"🛑 وقف (3%): `{price*0.97:.4f}`")
                send_to_all(msg)
    except Exception as e:
        print(f"Error in scanner: {e}")

# --- إعداد المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)

# 1. وظيفة فحص السوق (كل 15 دقيقة)
scheduler.add_job(scan_market, 'interval', minutes=15)

# 2. وظيفة "نبضة القلب" أو رسالة الحالة (كل 60 دقيقة)
scheduler.add_job(heart_beat_job, 'interval', minutes=60)

scheduler.start()

@app.route('/')
def home():
    return "Bot is Active! Monitoring Market & Sending Hourly Status."

if __name__ == "__main__":
    # إرسال رسالة ترحيبية وتنبيه بالأوضاع الجديدة
    send_to_all("🚀 **تم التحديث:**\nسأقوم الآن بإرسال رسالة تأكيد كل ساعة، بالإضافة للتوصيات عند توفر الشروط.")
    
    # تشغيل أول فحص يدوياً
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
