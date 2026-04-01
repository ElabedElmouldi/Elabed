import pandas as pd
import numpy as np
import requests
import time
import threading
import os
from flask import Flask

app = Flask(__name__)

# --- بياناتك التي تعمل على VS Code ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
CHAT_ID = "5067771509"
BASE_URL = "https://api1.binance.com"

@app.route('/')
def home():
    return "✅ Bot is Live and Scanning..."

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Log: {res.status_code}") # سيظهر في Render Logs
    except: pass

def run_scanner():
    """هذه الدالة هي المحرك الرئيسي"""
    print("🔎 بدء دورة فحص جديدة...")
    try:
        # جلب العملات
        resp = requests.get(f"{BASE_URL}/api/v3/ticker/24hr").json()
        symbols = [i['symbol'] for i in sorted(resp, key=lambda x: float(x['quoteVolume']), reverse=True) if i['symbol'].endswith('USDT')][:50]
        
        for symbol in symbols:
            # هنا يوضع منطق EMA و Volume و Fibonacci الذي كتبناه سابقاً
            # للتبسيط الآن سنطبع فقط أننا نفحص العملة
            print(f"Checking: {symbol}")
            time.sleep(0.2)
            
    except Exception as e:
        print(f"Error in Scanner: {e}")

def bot_worker():
    """دالة تعمل للأبد في الخلفية"""
    # إرسال رسالة فورية عند التشغيل للتأكد
    send_telegram_msg("🚀 البوت استيقظ الآن في سيرفر ألمانيا!")
    
    while True:
        run_scanner()
        print("💤 انتظار 30 دقيقة للفحص القادم...")
        time.sleep(1800) 

if __name__ == "__main__":
    # تشغيل البوت في خيط (Thread) منفصل تماماً
    t = threading.Thread(target=bot_worker, daemon=True)
    t.start()
    
    # تشغيل سيرفر الويب
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
