import pandas as pd
import numpy as np
import requests
import time
import threading
import os
from flask import Flask
import os
import threading
app = Flask(__name__)

# --- بياناتك التي تعمل على VS Code ---
TOKEN = 8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68ا"
CHAT_ID = "5067771509"
BASE_URL = "https://api1.binance.com"

# متغير للتأكد من أن البوت لا يعمل مرتين
bot_started = False

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Log: {res.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def scanner_engine():
    """المحرك الرئيسي للبوت"""
    send_telegram_msg("🚀 البوت انطلق الآن من سيرفر ألمانيا!")
    while True:
        try:
            print("🔎 جاري فحص السوق...")
            # هنا تضع كود الفحص الخاص بك (EMA, Volume, Fib)
            # ...
            print("✅ انتهى الفحص، انتظار 30 دقيقة...")
            time.sleep(1800)
        except Exception as e:
            print(f"Error in engine: {e}")
            time.sleep(60)

@app.route('/')
def home():
    global bot_started
    if not bot_started:
        # تشغيل المحرك فور فتح الرابط
        threading.Thread(target=scanner_engine, daemon=True).start()
        bot_started = True
        return "✅ Bot Started and Scanning..."
    return "✅ Bot is already Running..."

if __name__ == "__main__":
    # 1. تشغيل محرك الفحص في الخلفية فوراً
    # تأكد أن اسم الدالة التي تقوم بالفحص هي bot_worker أو scanner
    t = threading.Thread(target=bot_worker, daemon=True)
    t.start()
    
    # 2. تشغيل السيرفر (هذا السطر للمحلي فقط، Gunicorn سيتولى الأمر في Render)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
