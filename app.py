import os
import asyncio
import nest_asyncio
import telegram
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# حل مشكلة تداخل حلقات الأسنك
nest_asyncio.apply()

app = Flask(__name__)

# --- إعداداتك التي تأكدنا من صحتها ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ضعه_هنا")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضعه_هنا")

# --- الدوال الرياضية للمؤشرات ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / (loss + 1e-9) # إضافة رقم صغير لمنع القسمة على صفر
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(data, window=20, std_dev=2):
    sma = data.rolling(window=window).mean()
    std = data.rolling(window=window).std()
    return sma - (std * std_dev), sma + (std * std_dev)

async def send_telegram_msg(text):
    """إرسال الرسائل إلى تلجرام"""
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=int(CHAT_ID), text=text, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")

def scan_market():
    """البحث عن صفقات سبوت (+6% ربح)"""
    print("🔄 جاري مسح السوق بحثاً عن صفقات...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        # اختيار أفضل 20 عملة سيولة مقابل USDT
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP' not in s and 'DOWN' not in s]
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_20 = df_vol.sort_values(by='v', ascending=False).head(20)['s'].tolist()
        
        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب المؤشرات
            df['RSI'] = calculate_rsi(df['c'])
            df['Lower_BB'], _ = calculate_bollinger_bands(df['c'])
            
            last = df.iloc[-1]
            
            # --- استراتيجية الدخول ---
            # 1. RSI تحت 35 (تشبع بيعي)
            # 2. السعر لمس أو كسر خط البولنجر السفلي
            if not np.isnan(last['RSI']) and last['RSI'] < 35 and last['c'] <= last['Lower_BB']:
                entry = last['c']
                tp = entry * 1.06  # ربح 6%
                sl = entry * 0.97  # وقف 3%
                
                msg = (
                    f"🎯 **فرصة سبوت جديدة!**\n\n"
                    f"العملة: #{symbol.split('/')[0]}\n"
                    f"💵 **سعر الدخول:** `{entry:.4f}`\n"
                    f"🎯 **جني الأرباح (+6%):** `{tp:.4f}`\n"
                    f"🛑 **وقف الخسارة (-3%):** `{sl:.4f}`\n\n"
                    f"📊 RSI: {last['RSI']:.2f} | الفريم: 15m"
                )
                asyncio.run(send_telegram_msg(msg))

    except Exception as e:
        print(f"❌ خطأ أثناء المسح: {e}")

# --- المجدول الزمني ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=scan_market, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>البوت يعمل بنجاح!</h1><p>يتم فحص السوق كل 15 دقيقة وإرسال الإشعارات.</p>"

if __name__ == "__main__":
    # إرسال رسالة ترحيب فورية للتأكيد
    asyncio.run(send_telegram_msg("🤖 **تم تفعيل رادار الصفقات!**\nسأقوم بإعلامك فور العثور على فرصة ربح +6%."))
    
    # تشغيل أول مسح فوراً
    scan_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
