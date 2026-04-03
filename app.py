import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات (يجب ملؤها بدقة) ---
TOKEN = "ضـع_تـوكن_البـوت_هـنا"
CHAT_ID = "ضـع_ID_حسابك_هنا"

def send_telegram_msg(message):
    """دالة إرسال الرسائل مع نظام فحص الأخطاء"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"✅ تم الإرسال بنجاح")
        else:
            print(f"❌ خطأ من تلغرام: {response.text}")
    except Exception as e:
        print(f"⚠️ خطأ في الاتصال: {e}")

def main_strategy():
    """هنا سنضع خوارزمية الانفجار السعري لاحقاً"""
    print(f"[{datetime.now()}] جاري فحص السوق...")
    # مثال لرسالة تجريبية لمعرفة أن البوت يعمل
    # send_telegram_msg("🔄 البوت يقوم بفحص السوق الآن...")

# إعداد المجدول الزمني (يعمل كل 15 دقيقة)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(main_strategy, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Bot is Running!"

if __name__ == "__main__":
    # رسالة ترحيبية فورية عند التشغيل
    send_telegram_msg("🚀 **تم تفعيل البوت من جديد!**\nجاري مراقبة الانفجارات السعرية.")
    
    # تشغيل السيرفر
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
