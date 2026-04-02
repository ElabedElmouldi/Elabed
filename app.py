import os
import asyncio
import nest_asyncio
from flask import Flask
import telegram
import ccxt
import pandas as pd
import numpy as np  # سنستخدم numpy للحسابات الرياضية بدلاً من pandas-ta
from apscheduler.schedulers.background import BackgroundScheduler

nest_asyncio.apply()
app = Flask(__name__)

# إعدادات التلجرام
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ضـع_التوكـن_هـنا")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضـع_الشات_آيدي_هـنا")

# --- دالة حساب RSI يدوياً ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- دالة حساب Bollinger Bands يدوياً ---
def calculate_bollinger_bands(data, window=20, std_dev=2):
    sma = data.rolling(window=window).mean()
    std = data.rolling(window=window).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return lower_band, upper_band

async def send_msg(text):
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
    except Exception as e:
        print(f"Error sending message: {e}")

def analyze_market():
    print("🔍 جاري فحص السوق (حسابات يدوية)...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP' not in s and 'DOWN' not in s]
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_20 = df_vol.sort_values(by='v', ascending=False).head(20)['s'].tolist()
        
        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # حساب المؤشرات يدوياً
            df['RSI'] = calculate_rsi(df['c'])
            df['Lower_BB'], _ = calculate_bollinger_bands(df['c'])
            
            last_price = df['c'].iloc[-1]
            last_rsi = df['RSI'].iloc[-1]
            lower_band = df['Lower_BB'].iloc[-1]

            # شروط الاستراتيجية
            if not np.isnan(last_rsi) and last_rsi < 35 and last_price <= lower_band:
                tp = last_price * 1.06  # هدف 6%
                sl = last_price * 0.97  # وقف 3%
                
                message = (
                    f"🚀 **فرصة سبوت (Manual Calculation)**\n\n"
                    f"العملة: #{symbol.replace('/USDT', '')}\n"
                    f"💵 **سعر الدخول:** `{last_price:.4f}`\n"
                    f"🎯 **جني الأرباح (6%):** `{tp:.4f}`\n"
                    f"🛑 **وقف الخسارة (-3%):** `{sl:.4f}`\n\n"
                    f"RSI: {last_rsi:.2f}"
                )
                asyncio.run(send_msg(message))

    except Exception as e:
        print(f"Analysis Error: {e}")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=analyze_market, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "البوت يعمل ويقوم بمسح السوق يدوياً كل 15 دقيقة."

if __name__ == "__main__":
    # محاولة إرسال رسالة ترحيب فورا عند التشغيل
    try:
        asyncio.run(send_msg("🤖 **تم تشغيل البوت بنجاح!**\nجاري البحث عن صفقات باستخدام الحسابات الرياضية المباشرة..."))
    except: pass
    
    analyze_market()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
