import requests
import time
import http.server
import socketserver
import threading
import os

# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "5067771509"

# وظيفة لفتح منفذ وهمي لإرضاء Render ومنع خطأ الـ Port Scan
def start_dummy_server():
    # Render يمرر المنفذ عبر متغير بيئة اسمه PORT، وإلا نستخدم 10000
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    # السماح بإعادة استخدام المنفذ لتجنب أخطاء التوقف
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"✅ Dummy server started on port {port}")
        httpd.serve_forever()

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

if __name__ == "__main__":
    # 1. تشغيل الخادم الوهمي في الخلفية (Thread) لتجاوز فحص رندر
    thread = threading.Thread(target=start_dummy_server, daemon=True)
    thread.start()
    
    print("🚀 بدء تشغيل البوت...")
    
    # 2. إرسال رسالة التأكيد فوراً
    send_telegram_msg("✅ *تم إصلاح الكود وتجاوز مشكلة المنفذ!*\nالبوت يعمل الآن بشكل مستقر على Render.")

    # 3. حلقة العمل الدائمة
    while True:
        try:
            print("💎 البوت مستمر في العمل...")
            time.sleep(300) # فحص كل 5 دقائق
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(60)

