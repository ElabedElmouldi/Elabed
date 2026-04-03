import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)


# --- إعدادات التلجرام للمجموعة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

# أضف هنا أرقام الـ ID الخاصة بأصدقائك (تأكد أن كل صديق قد ضغط Start للبوت)
FRIENDS_IDS = [
    "5067771509", # الـ ID الخاص بك
    "2107567005", # الـ ID الصديق الأول
]


STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'EUR', 'USDS']

def send_to_all(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=10)
        except: pass

def calculate_indicators(df):
    # 1. حساب البولنجر باند
    df['MA20'] = df['c'].rolling(20).mean()
    df['STD'] = df['c'].rolling(20).std()
    df['Upper'] = df['MA20'] + (df['STD'] * 2)
    df['Lower'] = df['MA20'] - (df['STD'] * 2)
    df['Width'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100

    # 2. حساب RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    # 3. حساب ATR (لقياس التذبذب واحتساب الأهداف)
    df['H-L'] = df['h'] - df['l']
    df['H-PC'] = abs(df['h'] - df['c'].shift(1))
    df['L-PC'] = abs(df['l'] - df['c'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()

    return df

def scan_smart_explosion():
    print("🚀 جاري فحص السوق بالاستراتيجية الديناميكية...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            ticker = tickers[symbol]
            vol_24h = ticker['quoteVolume']

            # فلتر السيولة المتوسطة (النطاق المتفجر)
            if 10_000_000 <= vol_24h <= 300_000_000:
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                df = calculate_indicators(df)
                
                last = df.iloc[-1]
                
                # --- شروط الدخول الذكية ---
                # انضغاط حاد (< 1.2%) + قوة RSI (55-65)
                if last['Width'] < 1.2 and 55 <= last['RSI'] <= 65:
                    entry = last['c']
                    
                    # --- الحسابات الديناميكية ---
                    # الهدف: سعر الدخول + (3 أضعاف التذبذب ATR) لصيد انفجار كبير
                    target = entry + (last['ATR'] * 3)
                    # الوقف: خط البولنجر السفلي (دعم فني متحرك)
                    stop = last['Lower']
                    
                    # حساب النسبة المتوقعة للربح للتوضيح
                    profit_pct = ((target - entry) / entry) * 100

                    msg = (
                        f"🌋 **انفجار ذكي متوقع (ATR + BB)**\n"
                        f"العملة: #{symbol.replace('/USDT', '')}\n\n"
                        f"📊 **الضغط الفني:** `{last['Width']:.2f}%`\n"
                        f"📈 **قوة الزخم:** `{last['RSI']:.2f}`\n"
                        f"🌀 **معدل التذبذب (ATR):** `{last['ATR']:.4f}`\n\n"
                        f"📥 **سعر الدخول:** `{entry:.4f}`\n"
                        f"🎯 **الهدف الديناميكي:** `{target:.4f}` (~{profit_pct:.1f}%)\n"
                        f"🛑 **وقف الخسارة (BB):** `{stop:.4f}`\n\n"
                        f"💰 سيولة العملة: `${vol_24h/1e6:.1f}M`"
                    )
                    send_to_all(msg)

    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_smart_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Smart Strategy (ATR & Bollinger) is Live!"

if __name__ == "__main__":
    scan_smart_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
