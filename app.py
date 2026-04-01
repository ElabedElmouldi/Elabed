import pandas as pd
import numpy as np
import requests
import time
import threading
import os
from flask import Flask

# --- إعدادات الويب (لضمان استمرار السيرفر) ---
app = Flask(__name__)


@app.route('/')
def home():
    return "✅ Trading Bot is Running with EMA & Volume filters..."


# --- إعدادات البوت وتلغرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
CHAT_ID = "5067771509"
BASE_URL = "https://api1.binance.com"


def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload, timeout=15)
        # هذا السطر سيطبع نتيجة الإرسال في Logs الخاص بـ Render
        print(f"Telegram Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")


def get_data(symbol):
    # نطلب 250 شمعة لحساب EMA 200 بدقة
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval=1h&limit=250"
    try:
        res = requests.get(url, timeout=15)
        df = pd.DataFrame(res.json(), columns=['ts', 'open', 'high', 'low', 'close',
                          'vol', 'close_ts', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        df[['close', 'high', 'low', 'vol']] = df[['close', 'high', 'low', 'vol']].astype(float)
        return df
    except:
        return None


def analyze(df):
    # 1. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    # 2. EMA 200 (المتوسط المتحرك)
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    # 3. Fibonacci (آخر 100 شمعة)
    recent = df.iloc[-100:]
    high, low = recent['high'].max(), recent['low'].min()
    diff = high - low
    fib = {'0.5': high - 0.5 * diff, '0.618': high - 0.618 * diff, '0.786': high - 0.786 * diff}

    return df, fib


def run_scanner():
    url = f"{BASE_URL}/api/v3/ticker/24hr"
    try:
        symbols = [i['symbol'] for i in sorted(requests.get(url).json(), key=lambda x: float(
            x['quoteVolume']), reverse=True) if i['symbol'].endswith('USDT')][:50]
    except:
        return

    for symbol in symbols:
        df = get_data(symbol)
        if df is None or len(df) < 200:
            continue

        df, fib = analyze(df)
        cp = df['close'].iloc[-1]
        rsi = df['rsi'].iloc[-1]
        ema = df['ema200'].iloc[-1]

        # فلتر الفوليوم: حجم الشمعة الحالية > متوسط آخر 20 شمعة
        avg_vol = df['vol'].tail(20).mean()
        current_vol = df['vol'].iloc[-1]

        # --- الشروط المدمجة ---
        # 1. السعر في منطقة الارتداد (0.5 - 0.618)
        # 2. السعر فوق EMA 200 (اتجاه صاعد)
        # 3. RSI فوق 50 (زخم شرائي)
        # 4. الفوليوم أعلى من المتوسط (تأكيد سيولة)

        if (fib['0.5'] > cp > fib['0.618']) and (cp > ema) and (rsi > 50) and (current_vol > avg_vol):
            tp = cp * 1.05  # هدف 5%
            sl = fib['0.786']  # وقف الخسارة عند كسر منطقة فيبوناتشي

            msg = (f"🌟 **فرصة صعود قوية** 🌟\n\n"
                   f"💰 **العملة:** #{symbol}\n"
                   f"📍 **نقطة الدخول:** {cp:.4f}\n"
                   f"📈 **الهدف (TP):** {tp:.4f} (+5%)\n"
                   f"🛡️ **وقف الخسارة (SL):** {sl:.4f}\n\n"
                   f"📊 **المؤشرات:**\n"
                   f"• RSI: {rsi:.1f} (زخم إيجابي)\n"
                   f"• Trend: فوق EMA 200 (صاعد)\n"
                   f"• Volume: أعلى من المتوسط ✅")
            send_telegram_msg(msg)
            time.sleep(1)
        time.sleep(0.2)


def main_loop():
    send_telegram_msg("🚀 تم تشغيل الرادار بنجاح (EMA + Volume + Fib) ✅")
    while True:
        try:
            run_scanner()
        except:
            pass
        time.sleep(1800)


if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
