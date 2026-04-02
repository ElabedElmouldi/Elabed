import os
import asyncio
import nest_asyncio
from flask import Flask
import telegram
import ccxt
import pandas as pd
import pandas_ta as ta
from apscheduler.schedulers.background import BackgroundScheduler

nest_asyncio.apply()
app = Flask(__name__)

# إعدادات التلجرام
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضـع_الشات_آيدي_هـنا")

async def send_msg(text):
    """دالة مساعدة لإرسال الرسائل"""
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
    except Exception as e:
        print(f"Error sending message: {e}")

def analyze_market():
    """البحث عن صفقات وحساب الأهداف"""
    print("🔍 جاري فحص السوق الآن...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        # اختيار العملات الأعلى سيولة
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP' not in s and 'DOWN' not in s]
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_20 = df_vol.sort_values(by='v', ascending=False).head(20)['s'].tolist()
        
        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # المؤشرات: RSI و Bollinger Bands
            df['RSI'] = ta.rsi(df['c'], length=14)
            bb = ta.bbands(df['c'], length=20, std=2)
            
            last_price = df['c'].iloc[-1]
            last_rsi = df['RSI'].iloc[-1]
            lower_band = bb['BBL_20_2.0'].iloc[-1]

            # شرط الدخول: RSI منخفض + السعر عند أسفل البولنجر
            if last_rsi < 35 and last_price <= lower_band:
                # حساب الأهداف بناءً على طلبك
                take_profit = last_price * 1.06  # +6%
                stop_loss = last_price * 0.97    # -3%
                
                message = (
                    f"🚀 **تم العثور على صفقة سبوت!**\n\n"
                    f"العملة: #{symbol.replace('/USDT', '')}\n"
                    f"💵 **سعر الدخول:** `{last_price:.4f}`\n"
                    f"🎯 **جني الأرباح (6%):** `{take_profit:.4f}`\n"
                    f"🛑 **وقف الخسارة (-3%):** `{stop_loss:.4f}`\n\n"
                    f"RSI: {last_rsi:.2f} | الفريم: 15m"
                )
                asyncio.run(send_msg(message))

    except Exception as e:
        print(f"خطأ أثناء التحليل: {e}")

# المجدول الزمني كل 15 دقيقة
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=analyze_market, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "البوت يعمل ويقوم بمسح السوق كل 15 دقيقة."

if __name__ == "__main__":
    # 1. إرسال رسالة فورية عند تشغيل البوت
    asyncio.run(send_msg("🤖 **تم تشغيل البوت بنجاح!**\nجاري الآن مسح السوق كل 15 دقيقة للبحث عن أفضل الصفقات..."))
    
    # 2. تشغيل أول عملية فحص فوراً
    analyze_market()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
