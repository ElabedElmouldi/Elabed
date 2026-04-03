import os
import requests
from flask import Flask

app = Flask(__name__)

# --- إعدادات التلجرام ---
# استبدل التوكن والآيدي ببياناتك الخاصة
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
TARGET_ID = "5067771509"

def send_welcome_message():
    """دالة لإرسال رسالة الترحيب"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    message = "🚀 **أهلاً بك!**\nتم تشغيل البوت بنجاح وهو الآن متصل بالسيرفر."
    
    payload = {
        "chat_id": TARGET_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ تم إرسال رسالة الترحيب بنجاح!")
        else:
            print(f"❌ فشل الإرسال: {response.text}")
    except Exception as e:
        print(f"📡 خطأ في الاتصال: {e}")

@app.route('/')
def home():
    return "<h1>Bot is Online!</h1>"

if __name__ == "__main__":
    # إرسال الرسالة فور تشغيل الكود
    send_welcome_message()
    
    # تشغيل السيرفر (مهم جداً للمنصات السحابية)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
