import os
import asyncio
from flask import Flask
import telegram

app = Flask(__name__)

# --- ضع بياناتك هنا مباشرة ---
TOKEN = "ضع_التوكن_الخاص_بك_هنا"
CHAT_ID = "ضع_الشات_آيدي_الخاص_بك_هنا"
# ----------------------------

async def send_welcome():
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text="السلام عليكم تم تفعيل البوت بنجاح 🚀")
            print("✅ تم إرسال الرسالة بنجاح!")
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")

@app.route('/')
def home():
    # محاولة إرسال الرسالة عند فتح رابط الموقع للتأكيد
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_welcome())
    return "<h1>Bot is Active!</h1><p>Check your Telegram.</p>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
