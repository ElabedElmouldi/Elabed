import os
import asyncio
from flask import Flask
from telegram import Bot

# ================= إعدادات التلغرام الخاصة بك =================
TELEGRAM_TOKEN = '8ف439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68'
USER_ID = '5067771509'
# ==========================================================

app = Flask(__name__)


async def send_welcome_message():
    if TOKEN and CHAT_ID:
        bot = Bot(token=TOKEN)
        try:
            await bot.send_message(chat_id=CHAT_ID, text="السلام عليكم تم تفعيل البوت بنجاح 🚀")
            print("Message sent to Telegram!")
        except Exception as e:
            print(f"Error sending message: {e}")

@app.route('/')
def home():
    # عند زيارة الرابط، سيحاول البوت إرسال الرسالة للتأكيد
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_welcome_message())
    return "Bot is Active and Message Sent!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
