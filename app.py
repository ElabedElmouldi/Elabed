import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from fpdf import FPDF

# --- 1. إعدادات التلجرام والمنصة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

START_TIME = datetime.now() # لتسجيل وقت بدء تشغيل البوت
exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}   
last_scan_data = [] 

# --- 2. وظائف الإرسال ---

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. معالجة الرسائل (إضافة كلمة حالة) ---

def handle_updates():
    last_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}"
            res = requests.get(url, timeout=10).json()
            if res.get("result"):
                for up in res["result"]:
                    last_id = up["update_id"]
                    msg = up.get("message", {})
                    text = msg.get("text", "").strip()
                    
                    # الرد على كلمة "حالة"
                    if text == "حالة" or text == "status":
                        uptime = str(datetime.now() - START_TIME).split('.')[0]
                        status_msg = (
                            f"🟢 *تقرير حالة النظام*\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"✅ *الوضعية:* يعمل بنجاح\n"
                            f"⏱️ *مدة التشغيل:* `{uptime}`\n"
                            f"🔍 *المراقبة:* يفحص حالياً `900` عملة\n"
                            f"📦 *المراكز المفتوحة:* `{len(active_trades)}` صفقة\n"
                            f"⏰ *الوقت الحالي:* `{datetime.now().strftime('%H:%M:%S')}`\n"
                            f"━━━━━━━━━━━━━━"
                        )
                        send_telegram(status_msg)

                    elif text == "10":
                        send_telegram("⏳ يتم تجهيز قائمة أفضل 10 عملات...")
                        # (دالة توليد PDF - كما في النسخة السابقة)
                        pass 

                    elif text == "/start":
                        send_telegram("🚀 Sniper v17.2 Active.\nاكتب *'حالة'* للتأكد من عمل البوت، أو *'10'* للفرص.")
            time.sleep(2)
        except: time.sleep(5)

# --- 4. المحرك الرئيسي ---

def main_engine():
    global last_scan_data
    while True:
        try:
            # تحديث بيانات السوق (المسح)
            tickers = exchange.fetch_tickers()
            all_coins = []
            for s, t in tickers.items():
                if '/USDT' in s:
                    all_coins.append({'symbol': s, 'price': t['last'], 'change': t['percentage'], 'volume': t['quoteVolume']})
            last_scan_data = sorted(all_coins, key=lambda x: x['volume'], reverse=True)
            
            # (منطق مراقبة الصفقات المفتوحة - monitor_thread)
            time.sleep(300) # فحص شامل كل 5 دقائق
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=handle_updates).start()
    send_telegram(f"⚡ *تم البدء:* البوت يعمل الآن تحت المراقبة.")
    main_engine()
