
import os
import asyncio
from flask import Flask
import telegram

# ================= إعدادات التلغرام الخاصة بك =================
TELEGRAM_TOKEN = '8ف439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68'
USER_ID = '5067771509'
# =======================================================

app = Flask(__name__)

# جلب البيانات من إعدادات رندر
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

async def send_msg():
    if TOKEN and CHAT_ID:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text="السلام عليكم تم تفعيل البوت بنجاح 🚀")

@app.route('/')
def index():
    # محاولة إرسال الرسالة عند زيارة الرابط للتأكد
    try:
        asyncio.run(send_msg())
        return "Sent!"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
