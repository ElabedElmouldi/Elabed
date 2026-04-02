import os
import asyncio
import nest_asyncio
from flask import Flask
import telegram
import ccxt
import pandas as pd

# حل مشكلة تداخل حلقات الأسنك في البيئات السحابية
nest_asyncio.apply()

app = Flask(__name__)

# جلب البيانات من إعدادات رندر (أو ضعها يدوياً هنا للاختبار)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5067771509")

def get_top_20_liquidity():
    """جلب أكثر 20 عملة سيولة من باينانس خلال 24 ساعة"""
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        data = []
        for symbol, info in tickers.items():
            if symbol.endswith('/USDT'):
                data.append({
                    'symbol': symbol,
                    'volume': info['quoteVolume']  # السيولة بالدولار
                })
        
        df = pd.DataFrame(data)
        top_20 = df.sort_values(by='volume', ascending=False).head(20)
        
        message = "📊 *أعلى 20 عملة سيولة على باينانس (24h):*\n"
        message += "----------------------------------\n"
        for i, (idx, row) in enumerate(top_20.iterrows(), 1):
            vol_m = row['volume'] / 1_000_000
            message += f"{i}. *{row['symbol']}* ➔ `{vol_m:.1f}M$`\n"
        return message
    except Exception as e:
        return f"❌ خطأ في جلب البيانات: {str(e)}"

async def send_to_telegram(text):
    """إرسال التقرير إلى تلجرام"""
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
    report = get_top_20_liquidity()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_to_telegram(report))
    
    if success:
        return "<h1>✅ تم إرسال القائمة بنجاح!</h1>"
    else:
        return "<h1>❌ فشل في الإرسال - تحقق من التوكن والشات آيدي</h1>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
