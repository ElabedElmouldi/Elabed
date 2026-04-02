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
TELEGRAM_TOKEN = "8ف439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "-1003692815602"

exchange = ccxt.binance()
DATA_FILE = 'active_trades.json'

def load_active_trades():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return []

def save_active_trades(trades):
    with open(DATA_FILE, 'w') as f:
        json.dump(trades, f, indent=4)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except:
        print("خطأ في الاتصال بتلغرام")

def calculate_indicators(df):
    """حساب المؤشرات يدوياً لتجنب مشاكل المكتبات الخارجية"""
    # Bollinger Bands
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper_band'] = df['ma20'] + (df['std'] * 2)
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def check_signal(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df = calculate_indicators(df)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # شرط الاختراق: السعر الحالي اخترق البولينجر العلوي + RSI قوي
        if last['close'] > last['upper_band'] and prev['close'] <= prev['upper_band'] and last['rsi'] > 60:
            return True, last['close'], last['rsi']
    except: pass
    return False, 0, 0

def monitor_existing_trades():
    """مراقبة الصفقات المفتوحة لإرسال تنبيه عند الربح أو الخسارة"""
    active_trades = load_active_trades()
    still_open = []
    
    for trade in active_trades:
        try:
            ticker = exchange.fetch_ticker(trade['symbol'])
            curr_p = ticker['last']
            change = ((curr_p - trade['entry_price']) / trade['entry_price']) * 100
            
            if change >= 5.0:
                send_telegram(f"✅ *الهدف تحقق! (Target Hit)*\n💰 العملة: `{trade['symbol']}`\n📈 الربح: `+5%` \n💵 سعر الخروج: `{curr_p}`")
            elif change <= -2.5:
                send_telegram(f"🛑 *وقف الخسارة! (Stop Loss)*\n📉 العملة: `{trade['symbol']}`\n🔻 النتيجة: `-2.5%` \n💵 سعر الخروج: `{curr_p}`")
            else:
                still_open.append(trade)
        except:
            still_open.append(trade)
            
    save_active_trades(still_open)

def main():
    # 1. تنبيه عند التشغيل
    send_telegram("🚀 *بدأ البوت العمل الآن...*\nتم تفعيل نظام المراقبة اللحظي لـ 50 عملة.")
    
    while True:
        # 2. تنبيه عند بدء البحث في السوق (يظهر في Terminal فقط لعدم إزعاج القناة)
        print(f"🔎 جاري فحص السوق الآن: {datetime.now().strftime('%H:%M:%S')}")
        
        # مراقبة الصفقات المفتوحة
        monitor_existing_trades()
        
        # البحث عن فرص جديدة
        active_trades = load_active_trades()
        try:
            tickers = exchange.fetch_tickers()
            # فلترة العملات مقابل USDT فقط واستبعاد العملات المرفوعة (Leveraged tokens)
            symbols = [s for s in tickers if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
            top_50 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

            for sym in top_50:
                # التأكد أن العملة ليست مفتوحة مسبقاً
                if any(t['symbol'] == sym for t in active_trades):
                    continue
                
                is_valid, price, rsi_val = check_signal(sym)
                if is_valid:
                    # 3. تنبيه عند وجود صفقة
                    active_trades.append({"symbol": sym, "entry_price": price})
                    save_active_trades(active_trades)
                    
                    msg = (f"📥 *صفقة جديدة مكتشفة! (New Entry)*\n\n"
                           f"📊 العملة: `{sym}`\n"
                           f"💵 سعر الدخول: `{price}`\n"
                           f"📈 مؤشر RSI: `{rsi_val:.2f}`\n"
                           f"⏰ الوقت: `{datetime.now().strftime('%H:%M')}`")
                    send_telegram(msg)
                    
        except Exception as e:
            print(f"خطأ أثناء المسح: {e}")

        # فحص كل 10 دقائق (600 ثانية)
        time.sleep(600)

if __name__ == "__main__":
    main()
