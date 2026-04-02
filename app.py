import pandas as pd
import numpy as np
import requests
import time
import threading
import os
from flask import Flask
import os
import threading
app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))
app.run(host='0.0.0.0', port=port)


# --- بياناتك التي تعمل على VS Code ---
TOKEN = 8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68ا"
CHAT_ID = "5067771509"
BASE_URL = "https://api1.binance.com"


def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload, timeout=10)
    except: pass

def get_data(symbol):
    """جلب بيانات الشموع (فريم ساعة لصفقات السبوت)"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage" # مثال للربط، استخدم Binance API فعلياً هنا
    params = {'symbol': symbol, 'interval': '1h', 'limit': 100}
    res = requests.get("https://api.binance.com/api/v3/klines", params=params).json()
    df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'close_time', 'q_vol', 'trades', 't_base', 't_quote', 'ignore'])
    return df.astype(float)

def scanner_engine():
    send_telegram_msg("🚀 رادار السبوت يعمل الآن.. جاري صيد أهداف 5% و 10% 💎")
    
    while True:
        try:
            # جلب أفضل 30 عملة سيولة (Spot)
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
            symbols = [i['symbol'] for i in sorted(r, key=lambda x: float(x['quoteVolume']), reverse=True) if i['symbol'].endswith('USDT')][:30]
            
            for symbol in symbols:
                df = get_data(symbol)
                # حساب EMA 100 كفلتر اتجاه صاعد للسبوت
                df['ema100'] = df['close'].ewm(span=100).mean()
                last = df.iloc[-1]
                
                # شرط الدخول: السعر فوق المتوسط + فوليوم عالي + شمعة خضراء
                if last['close'] > last['ema100'] and last['vol'] > df['vol'].mean() * 1.3:
                    entry = float(last['close'])
                    tp5 = entry * 1.05
                    tp10 = entry * 1.10
                    stop = entry * 0.95 # وقف 5% لحماية رأس المال
                    
                    msg = (
                        f"💰 **فرصة سبوت جديدة: {symbol}**\n\n"
                        f"📊 سعر الدخول الحالي: `{entry:.4f}`\n"
                        f"📈 هدف أول (+5%): `{tp5:.4f}`\n"
                        f"🚀 هدف ثاني (+10%): `{tp10:.4f}`\n"
                        f"🛑 وقف الخسارة: `{stop:.4f}`\n\n"
                        f"💡 *نصيحة: يمكنك بيع نصف الكمية عند 5% وترك الباقي للـ 10%*"
                    )
                    send_telegram_msg(msg)
                    time.sleep(2) # تجنب الحظر

            print("✅ دورة فحص كاملة انتهت..")
            time.sleep(3600) # فحص كل ساعة (مناسب جداً للسبوت)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

@app.route('/')
def home():
    return "✅ Spot Trading Bot is Active..."

if __name__ == "__main__":
    threading.Thread(target=scanner_engine, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
