import json
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

CHAT_ID = "-1003692815602"


# إعداد المنصة (Binance)
exchange = ccxt.binance()

# ملف JSON لحفظ حالة الصفقات لضمان عدم ضياع البيانات عند إغلاق البرنامج
DATA_FILE = 'trading_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"active_trades": [], "completed_trades": [], "last_report_date": ""}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"خطأ في الإرسال للتلغرام: {e}")

def get_current_price(symbol):
    return exchange.fetch_ticker(symbol)['last']

def check_signal(symbol):
    """تحليل العملة: اختراق البولينجر العلوي + RSI > 60"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        
        # حساب المؤشرات
        bb = ta.bbands(df['c'], length=20, std=2)
        df['RSI'] = ta.rsi(df['c'], length=14)
        
        last_c = df['c'].iloc[-1]
        prev_c = df['c'].iloc[-2]
        upper_bb = bb['BBU_20_2.0'].iloc[-1]
        prev_upper = bb['BBU_20_2.0'].iloc[-2]
        current_rsi = df['RSI'].iloc[-1]

        # شرط الدخول: اختراق الخط العلوي للبولينجر مع زخم RSI
        if last_c > upper_bb and prev_c <= prev_upper and current_rsi > 60:
            return True, last_c
    except:
        pass
    return False, 0

def monitor_active_trades():
    """تحديث حالة الصفقات المفتوحة ومراقبة الربح/الخسارة"""
    data = load_data()
    updated_active = []
    
    for trade in data['active_trades']:
        try:
            current_p = get_current_price(trade['symbol'])
            change = ((current_p - trade['entry_price']) / trade['entry_price']) * 100
            
            # 1. هدف الربح 5%
            if change >= 5.0:
                trade['exit_price'] = current_p
                trade['result'] = "✅ +5.0%"
                trade['close_time'] = str(datetime.now())
                data['completed_trades'].append(trade)
                send_telegram(f"🎯 *تم تحقيق الهدف (5%)!*\nالعملة: `{trade['symbol']}`\nسعر الخروج: `{current_p}`")
            
            # 2. وقف الخسارة 2.5%
            elif change <= -2.5:
                trade['exit_price'] = current_p
                trade['result'] = "❌ -2.5%"
                trade['close_time'] = str(datetime.now())
                data['completed_trades'].append(trade)
                send_telegram(f"🛑 *ضرب وقف الخسارة (-2.5%)*\nالعملة: `{trade['symbol']}`\nسعر الخروج: `{current_p}`")
            
            else:
                # الصفقة لا تزال مفتوحة
                updated_active.append(trade)
        except:
            updated_active.append(trade)

    data['active_trades'] = updated_active
    save_data(data)

def send_daily_summary():
    """إرسال التقرير اليومي الشامل"""
    data = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    
    if data['last_report_date'] == today:
        return

    summary = f"📋 *تقرير التداول اليومي - {today}*\n\n"
    
    # الصفقات التي أغلقت اليوم
    summary += "✅ *الصفقات المكتملة اليوم:*\n"
    if not data['completed_trades']:
        summary += "_لا توجد صفقات منتهية_\n"
    for t in data['completed_trades']:
        summary += f"• `{t['symbol']}` ⬅️ {t['result']}\n"
    
    # الصفقات التي لا تزال مفتوحة
    summary += "\n⏳ *الصفقات المفتوحة حالياً:*\n"
    if not data['active_trades']:
        summary += "_لا توجد صفقات مفتوحة_\n"
    for t in data['active_trades']:
        curr_p = get_current_price(t['symbol'])
        p_diff = ((curr_p - t['entry_price']) / t['entry_price']) * 100
        summary += f"• `{t['symbol']}` | ربح/خسارة: `{p_diff:.2f}%`\n"

    send_telegram(summary)
    
    # تصفير القائمة المنتهية لليوم الجديد وتحديث التاريخ
    data['completed_trades'] = []
    data['last_report_date'] = today
    save_data(data)

def main():
    send_telegram("🤖 *تم تشغيل البوت المطور بنجاح... جاري مراقبة السوق!*")
    
    while True:
        # 1. تحديث ومراقبة الصفقات المفتوحة حالياً
        monitor_active_trades()
        
        # 2. البحث عن فرص جديدة (أفضل 50 عملة)
        data = load_data()
        try:
            tickers = exchange.fetch_tickers()
            symbols = [s for s in tickers if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
            top_50 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

            for sym in top_50:
                # لا تدخل في عملة مفتوحة حالياً
                if any(t['symbol'] == sym for t in data['active_trades']):
                    continue
                
                is_valid, entry_p = check_signal(sym)
                if is_valid:
                    new_trade = {
                        "symbol": sym, 
                        "entry_price": entry_p, 
                        "start_time": str(datetime.now())
                    }
                    data['active_trades'].append(new_trade)
                    save_data(data)
                    send_telegram(f"📥 *دخول صفقة جديدة:*\nالعملة: `{sym}`\nسعر الدخول: `{entry_p}`")
        except Exception as e:
            print(f"خطأ في مسح السوق: {e}")

        # 3. إرسال التقرير اليومي (الساعة 11 مساءً بتوقيتك)
        if datetime.now().hour == 23:
            send_daily_summary()

        print(f"دورة فحص مكتملة في {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(600) # فحص كل 10 دقائق

if __name__ == "__main__":
    main()

