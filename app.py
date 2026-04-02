import os
import asyncio
import nest_asyncio
from flask import Flask
import telegram

# حل مشكلة تداخل حلقات الأسنك
nest_asyncio.apply()

app = Flask(__name__)

# --- بياناتك الخاصة ---
# يفضل دائماً وضعها في إعدادات Render (Environment Variables) للأمان
TOKEN = os.environ.get("TELEGRAM_TOKEN", "ضـع_التوكـن_هـنا")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "ضـع_الشات_آيدي_هـنا")
# --------------------

async def send_welcome_msg():
    """إرسال رسالة الترحيب فقط"""
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text="السلام عليكم، تم تفعيل البوت بنجاح 🚀")
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False

@app.route('/')
def home():
    # محاولة إرسال الرسالة عند فتح الرابط
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_welcome_msg())
    
    if success:
        return "<h1>✅ البوت يعمل بنجاح!</h1><p>تم إرسال رسالة الترحيب إلى تلجرام.</p>"
    else:
        return "<h1>❌ فشل الإرسال</h1><p>تأكد من إعدادات التوكن والشات آيدي.</p>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

