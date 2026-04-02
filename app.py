import requests
import time
import http.server
import socketserver
import threading

# بيانات البوت
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
CHAT_ID = "6167826315"

# --- وظيفة لفتح منفذ وهمي لإرضاء Render ---
def start_dummy_server():
    PORT = 10000 # المنفذ الافتراضي في رندر
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=10)
    except: pass

if __name__ == "__main__":
    # تشغيل الخادم الوهمي في "خلفية الكود" (Thread)
    threading.Thread(target=start_dummy_server, daemon=True).交叉start()
    
    print("🚀 البوت بدأ العمل...")
    send_telegram_msg("✅ *البوت تجاوز مشكلة الـ Port بنجاح!*")

    while True:
        try:
            print("البوت لا يزال حياً...")
            time.sleep(300)
        except:
            time.sleep(60)
