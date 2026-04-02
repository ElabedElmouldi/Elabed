import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام (ضع بياناتك هنا) ---
TOKEN = "ضـع_التوكـن_هـنا"
CHAT_ID = "ضـع_الشات_آيدي_هـنا"

def send_telegram_msg(text):
    """وظيفة إرسال الرسالة إلى تلجرام"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"📡 Telegram Response: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

# --- إعداد المجدول الزمني ---
def job():
    print("⏰ حان موعد إرسال التنبيه...")
    send_telegram_msg("✅ السلام عليكم، البوت يعمل بنجاح")

scheduler = BackgroundScheduler(daemon=True)
# تعيين الفترة الزمنية كل 15 دقيقة
scheduler.add_job(func=job, trigger="interval", minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>البوت نشط!</h1><p>سيتم إرسال رسالة كل 15 دقيقة إلى تلجرام.</p>"

if __name__ == "__main__":
    # إرسال رسالة فورية عند تشغيل السيرفر للتأكد من الاتصال
    send_telegram_msg("🚀 تم تشغيل السيرفر بنجاح، سأرسل لك إشعاراً كل 15 دقيقة.")
    
    # تشغيل Flask
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
