import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message, reply_markup=None):
    """ دالة مطورة لإرسال الرسائل مع دعم الأزرار """
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            requests.post(url, json=payload, timeout=10)
        except: pass

# --- 2. إنشاء لوحة الأزرار (Keyboard) ---
def get_main_keyboard():
    # إنشاء أزرار ثابتة تظهر للمستخدم في التلجرام
    return {
        "keyboard": [
            [{"text": "📊 تقرير الصفقات المفتوحة"}, {"text": "✅ صفقات اليوم المغلقة"}],
            [{"text": "🔄 تحديث الحالة"}, {"text": "💰 الرصيد الحالي"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# --- 3. وظائف التقارير (التي ستستدعيها الأزرار) ---
def get_open_trades_report():
    if not active_trades:
        return "📭 لا توجد صفقات مفتوحة حالياً."
    
    report = "📊 *تقرير الصفقات المفتوحة*\n━━━━━━━━━━━━━━\n"
    for s, d in active_trades.items():
        try:
            ticker = exchange.fetch_ticker(s)
            pnl = ((ticker['last'] - d['entry']) / d['entry']) * 100
            report += f"🪙 `{s}`: `{pnl:+.2f}%` | 📥 `{d['entry']}`\n"
        except: pass
    return report

def get_closed_trades_report():
    if not closed_today:
        return "📅 لم يتم إغلاق أي صفقات اليوم بعد."
    
    report = "✅ *الصفقات المغلقة اليوم*\n━━━━━━━━━━━━━━\n"
    total = 0
    for t in closed_today:
        report += f"🔹 `{t['symbol']}`: `{t['pnl']:+.2f}%`\n"
        total += t['pnl']
    report += f"━━━━━━━━━━━━━━\n📈 الإجمالي: `{total:+.2f}%`"
    return report

# --- 4. استقبال أوامر الأزرار (Webhook/Polling) ---
def check_telegram_updates():
    """ دالة لمراقبة ضغطات الأزرار من قبلك """
    last_update_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}"
            response = requests.get(url, timeout=10).json()
            if response.get("result"):
                for update in response["result"]:
                    last_update_id = update["update_id"]
                    if "message" in update:
                        text = update["message"].get("text")
                        
                        if text == "📊 تقرير الصفقات المفتوحة":
                            send_telegram(get_open_trades_report(), get_main_keyboard())
                        elif text == "✅ صفقات اليوم المغلقة":
                            send_telegram(get_closed_trades_report(), get_main_keyboard())
                        elif text == "/start":
                            send_telegram("👋 أهلاً بك يا مولدي في لوحة تحكم القناص v16.7", get_main_keyboard())
            time.sleep(2)
        except: time.sleep(5)

# --- 5. الإعدادات المالية والمسح (نفس المنطق السابق) ---
MAX_TRADES = 10
TRADE_VALUE_USD = 100
exchange = ccxt.binance({'enableRateLimit': True})
active_trades = {}
closed_today = []

# (ملاحظة: يتم استكمال بقية وظائف المسح والمراقبة من النسخة v16.6 هنا)
# ... [monitor_thread و main_engine] ...

if __name__ == "__main__":
    # تشغيل سيرفر ويب
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    
    # خيط مراقبة الأزرار (جديد)
    Thread(target=check_telegram_updates).start()
    
    # خيط مراقبة الصفقات
    # Thread(target=monitor_thread).start()
    
    # بدء المحرك الرئيسي مع إرسال الأزرار لأول مرة
    send_telegram("🚀 *تم تفعيل Sniper v16.7*\nلوحة التحكم جاهزة أسفل الشاشة.", get_main_keyboard())
    # main_engine()
