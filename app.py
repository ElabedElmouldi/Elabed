import requests
import os
import time

# جلب الإعدادات من إعدادات البيئة في رندر
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("خطأ: تأكد من إضافة TELEGRAM_TOKEN و CHAT_ID في إعدادات Render")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"خطأ أثناء الإرسال: {e}")

if __name__ == "__main__":
    print("🚀 البوت بدأ العمل...")
    
    # رسالة ترحيبية تخبرك أن البوت يعمل
    send_telegram_msg("🔔 *نظام التداول يعمل الآن!*\nالبوت متصل بنجاح وسيبدأ بمراقبة السوق فور إضافة الاستراتيجية.")

    # حلقة تكرار بسيطة للبقاء قيد التشغيل
    while True:
        try:
            print("✅ البوت لا يزال قيد التشغيل...")
            # اختيارياً: يمكنك ترك هذه الرسالة أو حذفها لاحقاً
            # send_telegram_msg("🔄 تحديث: البوت لا يزال يعمل في الخلفية.")
            
            # الانتظار لمدة 10 دقائق (600 ثانية)
            time.sleep(600)
        except Exception as e:
            print(f"حدث خطأ في الحلقة: {e}")
            time.sleep(60)
