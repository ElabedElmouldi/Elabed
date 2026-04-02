import os
import asyncio
import nest_asyncio
from flask import Flask
import telegram
import ccxt
import pandas as pd
import pandas_ta as ta

nest_asyncio.apply()
app = Flask(__name__)

# بياناتك الخاصة (يفضل وضعها في إعدادات Render)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5067771509")

def analyze_logic():
    try:
        exchange = ccxt.binance()
        # جلب أعلى 20 عملة سيولة لضمان دقة المؤشرات
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT')]
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_20 = df_vol.sort_values(by='v', ascending=False).head(20)['s'].tolist()
        
        signals = []

        for symbol in top_20:
            bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=300)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # --- حساب المؤشرات الفنية ---
            df['EMA_9'] = ta.ema(df['c'], length=9)
            df['EMA_21'] = ta.ema(df['c'], length=21)
            df['EMA_200'] = ta.ema(df['c'], length=200)
            df['RSI'] = ta.rsi(df['c'], length=14)
            
            # Bollinger Bands
            bbands = ta.bbands(df['c'], length=20, std=2)
            df['BB_Lower'] = bbands['BBL_20_2.0']
            df['BB_Upper'] = bbands['BBU_20_2.0']

            # بيانات الشمعة الأخيرة
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- منطق الاستراتيجية (شروط الشراء المحتملة) ---
            # 1. الاتجاه العام صاعد (السعر فوق EMA 200)
            is_uptrend = last['c'] > last['EMA_200']
            # 2. تقاطع إيجابي (EMA 9 فوق EMA 21)
            is_golden_cross = last['EMA_9'] > last['EMA_21']
            # 3. ارتداد من أسفل البولنجر أو RSI منخفض
            is_oversold = last['c'] <= last['BB_Lower'] or last['RSI'] < 40
            # 4. زيادة في حجم التداول (Volume) مقارنة بالمتوسط
            avg_vol = df['v'].tail(20).mean()
            high_vol = last['v'] > avg_vol

            if is_uptrend and is_golden_cross and is_oversold:
                signals.append(
                    f"🚀 **إشارة شراء محتملة: {symbol}**\n"
                    f"• السعر: `{last['c']}`\n"
                    f"• RSI: `{last['RSI']:.2f}`\n"
                    f"• الاتجاه: فوق EMA 200 (إيجابي)\n"
                    f"• التذبذب: ارتداد من قاع Bollinger\n"
                    f"• الهدف المتوقع: `{last['c'] * 1.05:.4f}` (+5%)"
                )

        return "\n\n".join(signals) if signals else "⏳ السوق في حالة ترقب، لا توجد فرص تطابق كامل الشروط حالياً."

    except Exception as e:
        return f"❌ خطأ فني: {str(e)}"

async def send_to_telegram(text):
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
            return True
    except Exception as e:
        print(f"Telegram Error: {e}")
        return False

@app.route('/')
def home():
    report = analyze_logic()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_to_telegram(report))
    return f"<h1>✅ تم الفحص بنجاح</h1><pre>{report}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
