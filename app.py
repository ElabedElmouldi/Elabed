
import ccxt
import pandas as pd
import requests
import time
import os
import threading
import http.server
import socketserver
from datetime import datetime

# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "1003692815602"


# إعداد المنصة
exchange = ccxt.binance()

# ملف لتخزين البيانات
DATA_FILE = 'trades_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"active_trades": [], "completed_trades": [], "last_report_date": ""}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def get_current_price(symbol):
    ticker = exchange.fetch_ticker(symbol)
    return ticker['last']

def update_trades_status():
    data = load_data()
    updated_active = []
    
    for trade in data['active_trades']:
        try:
            current_price = get_current_price(trade['symbol'])
            price_change = ((current_price - trade['entry_price']) / trade['entry_price']) * 100
            
            # تحديث النتيجة إذا تحقق الهدف أو الوقف
            if price_change >= 5.0:
                trade['status'] = '✅ ربح (Target hit)'
                trade['exit_price'] = current_price
                trade['result'] = "+5%"
                data['completed_trades'].append(trade)
            elif price_change <= -2.5:
                trade['status'] = '❌ خسارة (Stop hit)'
                trade['exit_price'] = current_price
                trade['result'] = "-2.5%"
                data['completed_trades'].append(trade)
            else:
                updated_active.append(trade) # لا تزال مفتوحة
        except:
            updated_active.append(trade)
            
    data['active_trades'] = updated_active
    save_data(data)

def send_daily_report():
    data = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    
    if data['last_report_date'] == today:
        return # تم إرسال التقرير اليوم بالفعل

    report = f"📋 *التقرير اليومي للصفقات - {today}*\n\n"
    
    # 1. الصفقات المكتملة اليوم
    report += "✅ *الصفقات المنتهية:* \n"
    if not data['completed_trades']:
        report += "- لا توجد صفقات منتهية بعد.\n"
    for t in data['completed_trades']:
        report += f"• `{t['symbol']}` | النتيجة: *{t['result']}*\n"
    
    # 2. الصفقات المفتوحة حالياً
    report += "\n⏳ *الصفقات المفتوحة:* \n"
    if not data['active_trades']:
        report += "- لا توجد صفقات مفتوحة.\n"
    for t in data['active_trades']:
        curr_p = get_current_price(t['symbol'])
        p_diff = ((curr_p - t['entry_price']) / t['entry_price']) * 100
        report += f"• `{t['symbol']}` | الربح الحالي: `{p_diff:.2f}%`\n"

    send_telegram_msg(report)
    
    # تفريغ الصفقات المنتهية لليوم القادم وتحديث تاريخ التقرير
    data['completed_trades'] = []
    data['last_report_date'] = today
    save_data(data)

def run_scanner():
    data = load_data()
    # جلب أفضل 50 عملة
    markets = exchange.fetch_tickers()
    symbols = [s for s in markets if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
    sorted_symbols = sorted(symbols, key=lambda x: markets[x]['quoteVolume'], reverse=True)[:50]

    for symbol in sorted_symbols:
        # منع الدخول في عملة مفتوحة حالياً أو دخلنا فيها اليوم
        if any(t['symbol'] == symbol for t in data['active_trades']):
            continue

        # (نفس دالة التحليل السابقة analyze_signal تضاف هنا)
        # إذا تحقق الشرط:
        # entry_p = get_current_price(symbol)
        # new_trade = {"symbol": symbol, "entry_price": entry_p, "time": str(datetime.now())}
        # data['active_trades'].append(new_trade)
        # send_telegram_msg(f"🚀 دخول صفقة جديدة: {symbol} بسعر {entry_p}")
    
    save_data(data)

# دورة العمل الرئيسية
while True:
    update_trades_status() # تحديث حالة الصفقات المفتوحة
    run_scanner()          # البحث عن فرص جديدة
    
    # إرسال التقرير في وقت محدد (مثلاً الساعة 11 مساءً)
    if datetime.now().hour == 23:
        send_daily_report()
        
    time.sleep(900) # فحص كل 15 دقيقة


