import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from fpdf import FPDF

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

# --- 2. الإعدادات المالية ---
MAX_TRADES = 10
TRADE_VALUE_USD = 100
ACTIVATION_PROFIT = 0.05 
TRAILING_GAP = 0.02      
STOP_LOSS_PCT = 0.04     

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}   
closed_today = []    

# --- 3. وظائف التلجرام والأزرار ---

def send_telegram(message, reply_markup=None):
    """ إرسال رسائل نصية مع أزرار تفاعلية """
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": reply_markup
            }
            requests.post(url, json=payload, timeout=10)
        except: pass

def send_telegram_file(file_path, caption):
    """ إرسال ملف PDF """
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
            with open(file_path, 'rb') as f:
                requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files={'document': f})
        except: pass

def get_control_buttons():
    """ إنشاء أزرار تظهر تحت الرسالة مباشرة لضمان رؤيتها """
    return {
        "inline_keyboard": [
            [{"text": "📊 تقرير المفتوح", "callback_data": "open_report"}, 
             {"text": "✅ صفقات اليوم", "callback_data": "closed_report"}],
            [{"text": "📄 استخراج PDF (طباعة)", "callback_data": "pdf_report"}]
        ]
    }

# --- 4. نظام التقارير والـ PDF ---

def generate_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Daily Trading Report - Sniper v16.9", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align='C')
    pdf.ln(10)
    
    # جدول الصفقات
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 10, "Symbol", 1); pdf.cell(30, 10, "Entry", 1); pdf.cell(30, 10, "Exit", 1)
    pdf.cell(30, 10, "PnL %", 1); pdf.cell(60, 10, "Time (In > Out)", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    total_pnl = 0
    for t in closed_today:
        pdf.cell(40, 10, t['symbol'], 1)
        pdf.cell(30, 10, str(t['entry']), 1)
        pdf.cell(30, 10, str(t['exit']), 1)
        pdf.cell(30, 10, f"{t['pnl']:+.2f}%", 1)
        pdf.cell(60, 10, f"{t['time_in']} > {t['time_out']}", 1)
        pdf.ln()
        total_pnl += t['pnl']
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Total Daily Profit: {total_pnl:+.2f}%", ln=True)
    
    file_name = f"Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(file_name)
    return file_name

# --- 5. محرك التتبع والمراقبة (10 ثوانٍ) ---

def monitor_thread():
    while True:
        try:
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                trade = active_trades[symbol]
                
                if cp > trade['highest_price']: active_trades[symbol]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                highest = active_trades[symbol]['highest_price']
                drop = (highest - cp) / highest
                
                exit_triggered = False
                reason = ""
                if gain <= -STOP_LOSS_PCT:
                    exit_triggered = True; reason = "STOP LOSS"
                elif gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP:
                    exit_triggered = True; reason = "TRAILING TP"

                if exit_triggered:
                    pnl_val = gain * 100
                    # إشعار الخروج التفصيلي
                    duration = str(datetime.now() - datetime.strptime(trade['time'], '%H:%M:%S')).split('.')[0]
                    exit_msg = (
                        f"🏁 *خروج من صفقة*\n━━━━━━━━━━━━━━\n"
                        f"🪙 `{symbol}`\n📥 دخول: `{trade['entry']}` | 📤 خروج: `{cp}`\n"
                        f"📊 النتيجة: `{pnl_val:+.2f}%` | ⏳ المدة: `{duration}`"
                    )
                    send_telegram(exit_msg, get_control_buttons())
                    
                    closed_today.append({
                        'symbol': symbol, 'entry': trade['entry'], 'exit': cp,
                        'pnl': pnl_val, 'time_in': trade['time'], 'time_out': datetime.now().strftime('%H:%M:%S')
                    })
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(5)

# --- 6. معالجة ضغطات الأزرار (Callback Queries) ---

def handle_updates():
    last_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}"
            res = requests.get(url, timeout=10).json()
            if res.get("result"):
                for up in res["result"]:
                    last_id = up["update_id"]
                    
                    # معالجة الضغط على الأزرار (Callback)
                    if "callback_query" in up:
                        data = up["callback_query"]["data"]
                        if data == "pdf_report":
                            send_telegram("⏳ يتم الآن إنشاء ملف PDF...")
                            f_path = generate_pdf()
                            send_telegram_file(f_path, "📑 تقرير التداول اليومي")
                            if os.path.exists(f_path): os.remove(f_path)
                        elif data == "open_report":
                            msg = "📊 *الصفقات المفتوحة:*\n"
                            if not active_trades: msg += "_لا يوجد_\n"
                            for s, v in active_trades.items():
                                msg += f"🪙 `{s}` | دخول: `{v['entry']}`\n"
                            send_telegram(msg, get_control_buttons())
                    
                    # معالجة الأوامر النصية
                    elif "message" in up and "text" in up["message"]:
                        if up["message"]["text"] == "/start":
                            send_telegram("🚀 أهلاً بك مولدي. لوحة التحكم جاهزة:", get_control_buttons())
            time.sleep(2)
        except: time.sleep(5)

# --- 7. المحرك الرئيسي للمسح ---

def main_engine():
    send_telegram("🚀 *تم تشغيل Sniper v16.9*\nالمسح (900 عملة) والتتبع (2%) مفعّل.", get_control_buttons())
    last_scan = datetime.now() - timedelta(minutes=10)
    
    while True:
        try:
            now = datetime.now()
            if now >= last_scan + timedelta(minutes=10):
                tickers = exchange.fetch_tickers()
                targets = sorted([s for s in tickers.keys() if '/USDT' in s], key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
                
                for s in targets:
                    if len(active_trades) < MAX_TRADES and s not in active_trades:
                        # شرط دخول مبسط (يمكنك تعديل الـ 20 شرطاً هنا)
                        if tickers[s]['percentage'] > 2: # مثال: صعود أكثر من 2%
                            p = tickers[s]['last']
                            start_t = now.strftime('%H:%M:%S')
                            active_trades[s] = {'entry': p, 'highest_price': p, 'time': start_t}
                            
                            entry_msg = (
                                f"🔔 *دخول صفقة*\n━━━━━━━━━━━━━━\n"
                                f"🪙 `{s}` | 💰 سعر: `{p}`\n"
                                f"💵 القيمة: `${TRADE_VALUE_USD}` | ⏰: `{start_t}`"
                            )
                            send_telegram(entry_msg, get_control_buttons())
                    time.sleep(0.04)
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=handle_updates).start()
    Thread(target=monitor_thread).start()
    main_engine()
