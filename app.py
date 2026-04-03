import os
import requests
import ccxt
import pandas as pd
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- الإعدادات (تأكد من صحة البيانات) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
TARGET_ID = "5067771509" 

def send_telegram_message(message):
    """دالة إرسال الرسائل مع نظام التحقق من الأخطاء"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Response: {response.json()}")
    except Exception as e:
        print(f"Network Error: {e}")

def scan_market():
    """الدالة المسؤولة عن فحص العملات"""
    print("🔎 فحص السوق دوري يعمل الآن...")
    # هنا تضع منطق فحص العملات (RSI والبولنجر) الذي أعددناه سابقاً
    pass

# إعداد المجدول ليعمل في الخلفية
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "<h1>Bot Status: Online</h1>"

if __name__ == "__main__":
    # --- هذه هي الرسالة التي طلبتها (ترسل فور تشغيل الكود) ---
    send_telegram_message("🚀 **البوت يعمل الآن على السيرفر!**\nنظام فحص العملات البديلة نشط.")
    
    # تحديد المنفذ (مهم جداً للمنصات السحابية)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
