import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)


# --- إعدادات التلجرام للمجموعة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

# أضف هنا أرقام الـ ID الخاصة بأصدقائك (تأكد أن كل صديق قد ضغط Start للبوت)
FRIENDS_IDS = [
    "5067771509", # الـ ID الخاص بك
    "2107567005", # الـ ID الصديق الأول
]

STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USDS', 'EUR']

def send_to_all(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=10)
        except: pass

def send_heartbeat():
    now = datetime.now().strftime('%H:%M')
    msg = f"🤖 **تحديث الحالة:**\nأنا أعمل بنشاط وأراقب السوق الآن. (توقيت تونس: {now})"
    send_to_all(msg)

def get_data(exchange, symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    except: return pd.DataFrame()

def calculate_advanced_indicators(df):
    if df.empty: return df
    # البولنجر باند
    df['MA20'] = df['c'].rolling(20).mean()
    df['STD'] = df['c'].rolling(20).std()
    df['Lower'] = df['MA20'] - (df['STD'] * 2)
    df['Width'] = (df['STD'] * 4) / df['MA20'] * 100

    # RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    # CMF & ATR
    mfv = ((df['c'] - df['l']) - (df['h'] - df['c'])) / (df['h'] - df['l'] + 1e-9) * df['v']
    df['CMF'] = mfv.rolling(20).sum() / (df['v'].rolling(20).sum() + 1e-9)
    df['TR'] = np.maximum((df['h'] - df['l']), np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['ATR'] = df['TR'].rolling(14).mean()
    return df

def scan_professional_v4_1():
    print("🔎 جاري فحص السوق وإعداد التقارير...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            vol_24h = tickers[symbol]['quoteVolume']
            # فلتر السيولة (نطاق العملات القابلة للانفجار)
            if 10_000_000 <= vol_24h <= 300_000_000:
                df_4h = get_data(exchange, symbol, '4h', 50)
                if df_4h.empty: continue
                
                # تأكيد الاتجاه الصاعد على 4 ساعات
                ema_50_4h = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                if df_4h['c'].iloc[-1] > ema_50_4h:
                    
                    df_15m = get_data(exchange, symbol, '15m', 100)
                    df_15m = calculate_advanced_indicators(df_15m)
                    if df_15m.empty: continue
                    last = df_15m.iloc[-1]

                    # شروط الانفجار: ضغط < 1.2% | RSI صاعد | تدفق سيولة إيجابي
                    if last['Width'] < 1.2 and 55 <= last['RSI'] <= 65 and last['CMF'] > 0:
                        entry = last['c']
                        target = entry + (last['ATR'] * 3) # الهدف بناء على التذبذب
                        stop = last['Lower']              # الوقف فني تحت البولنجر
                        
                        # حساب النسب المئوية
                        profit_pct = ((target - entry) / entry) * 100
                        loss_pct = ((entry - stop) / entry) * 100
                        risk_reward = profit_pct / loss_pct if loss_pct != 0 else 0

                        # لا نرسل إلا إذا كان الربح المتوقع أكبر من 5%
                        if profit_pct >= 5.0:
                            msg = (
                                f"🚀 **إشارة انفجار سعري جديدة**\n"
                                f"العملة: #{symbol.replace('/USDT', '')}\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📥 **نقطة الدخول:** `{entry:.4f}`\n"
                                f"🛑 **وقف الخسارة:** `{stop:.4f}` ({loss_pct:.1f}-%)\n"
                                f"🎯 **الهدف المتوقع:** `{target:.4f}` (+{profit_pct:.1f}%)\n"
                                f"⚖️ **معدل الربح/المخاطرة:** `1:{risk_reward:.1f}`\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📊 **المؤشرات:**\n"
                                f"• RSI: `{last['RSI']:.1f}`\n"
                                f"• تدفق الأموال CMF: `{last['CMF']:.2f}`\n"
                                f"• سيولة 24h: `${vol_24h/1e6:.1f}M`"
                            )
                            send_to_all(msg)
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_professional_v4_1, 'interval', minutes=15)
scheduler.add_job(send_heartbeat, 'interval', hours=2)
scheduler.start()

@app.route('/')
def home():
    return "Bot V4.1: Entry, Stop, and Profit % Display Active!"

if __name__ == "__main__":
    send_to_all("🚀 **تم تفعيل رادار الانفجار V4.1**\n- عرض الدخول والوقف بدقة.\n- حساب نسبة الربح المتوقعة آلياً.")
    scan_professional_v4_1()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
