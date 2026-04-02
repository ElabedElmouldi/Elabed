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

# إعدادات الحساب (يفضل وضعها في Environment Variables في Render)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضـع_الشات_آيدي_هـنا")

def find_spot_opportunities():
    """استراتيجية البحث عن ارتداد 5% في سوق السبوت"""
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        # فلترة العملات المستقرة والتركيز على السيولة العالية مقابل USDT
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP' not in s and 'DOWN' not in s]
        df_vol = pd.DataFrame([{'s': s, 'v': tickers[s]['quoteVolume']} for s in symbols])
        top_20 = df_vol.sort_values(by='v', ascending=False).head(20)['s'].tolist()
        
        opportunities = []

        for symbol in top_20:
            # جلب بيانات 4 ساعات لتحليل الاتجاه القوي
            bars = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # --- المؤشرات الفنية ---
            df['EMA_200'] = ta.ema(df['c'], length=200) # الاتجاه طويل الأمد
            df['EMA_21'] = ta.ema(df['c'], length=21)   # الاتجاه المتوسط
            df['RSI'] = ta.rsi(df['c'], length=14)
            bbands = ta.bbands(df['c'], length=20, std=2)
            
            last = df.iloc[-1]
            
            # --- منطق استراتيجية الـ 5% ربح ---
            # 1. السعر في منطقة دعم (قريب من EMA 200 أو أسفل البولنجر)
            at_support = last['c'] <= last['EMA_200'] * 1.02 or last['c'] <= bbands['BBL_20_2.0'].iloc[-1]
            
            # 2. مؤشر RSI يشير إلى تشبع بيعي أو بداية ارتداد (تحت 40)
            oversold = last['RSI'] < 40
            
            # 3. حجم تداول أعلى من المتوسط (دخول سيولة)
            high_volume = last['v'] > df['v'].tail(10).mean()

            if at_support and oversold and high_volume:
                target = last['c'] * 1.05
                opportunities.append(
                    f"🎯 **فرصة سبوت (هدف +5%): {symbol}**\n"
                    f"• السعر الحالي: `{last['c']}`\n"
                    f"• RSI: `{last['RSI']:.2f}`\n"
                    f"• الدعم: السعر عند منطقة ارتداد قوية\n"
                    f"• الهدف الأول: `{target:.4f}`"
                )

        return "\n\n".join(opportunities) if opportunities else "⏳ لا توجد فرص سبوت مطابقة للشروط حالياً."

    except Exception as e:
        return f"❌ خطأ في التحليل: {str(e)}"

async def send_to_telegram(text):
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False

@app.route('/')
def home():
    report = find_spot_opportunities()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_to_telegram(report))
    return f"<h1>✅ تم فحص السوق</h1><pre>{report}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
