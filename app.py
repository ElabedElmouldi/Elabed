import os, asyncio, telegram, nest_asyncio
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

nest_asyncio.apply()
app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5067771509")

async def send_test():
    try:
        bot = telegram.Bot(token=TOKEN)
        async with bot:
            await bot.send_message(chat_id=CHAT_ID, text="🔔 اختبار: البوت متصل ويرسل رسائل!")
            print("✅ Sent!")
    except Exception as e:
        print(f"❌ Error: {e}")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=lambda: asyncio.run(send_test()), trigger="interval", minutes=1)
scheduler.start()

@app.route('/')
def index(): return "Status: Online"

if __name__ == "__main__":
    asyncio.run(send_test()) # إرسال فور التشغيل
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
