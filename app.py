import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام ---
TOKEN = "ضـع_تـوكن_البـوت_هـنا"
FRIENDS_IDS = ["ID1", "ID2"] # أضف الـ IDs هنا

STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USDS']

def send_to_all(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=10)
        except: pass

def get_data(exchange, symbol, timeframe, limit=100):
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    return df

def calculate_advanced_indicators(df):
    # 1. البولنجر باند
    df['MA20'] = df['c'].rolling(20).mean()
    df['STD'] = df['c'].rolling(20).std()
    df['Upper'] = df['MA20'] + (df['STD'] * 2)
    df['Lower'] = df['MA20'] - (df['STD'] * 2)
    df['Width'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100

    # 2. RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    # 3. Chaikin Money Flow (CMF) - تدفق السيولة
    mfv = ((df['c'] - df['l']) - (df['h'] - df['c'])) / (df['h'] - df['l'] + 1e-9) * df['v']
    df['CMF'] = mfv.rolling(20).sum() / df['v'].rolling(20).sum()

    # 4. ATR للأهداف
    df['TR'] = np.maximum((df['h'] - df['l']), 
                          np.maximum(abs(df['h'] - df['c'].shift(1)), 
                                     abs(df['l'] - df['c'].shift(1))))
    df['ATR'] = df['TR'].rolling(14).mean()
    
    return df

def scan_professional_pro():
    print("💎 جاري فحص الفرص بنظام الفلاتر المركبة...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            vol_24h = tickers[symbol]['quoteVolume']

            # فلتر السيولة (10M - 300M)
            if 10_000_000 <= vol_24h <= 300_000_000:
                # أ- فحص الفريم الكبير (4 ساعات) لتأكيد الاتجاه
                df_4h = get_data(exchange, symbol, '4h', 50)
                ema_50_4h = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                current_price_4h = df_4h['c'].iloc[-1]

                # شرط ذهبي: السعر يجب أن يكون فوق EMA 50 على الـ 4 ساعات
                if current_price_4h > ema_50_4h:
                    
                    # ب- فحص الفريم الصغير (15 دقيقة) للتنفيذ
                    df_15m = get_data(exchange, symbol, '15m', 100)
                    df_15m = calculate_advanced_indicators(df_15m)
                    last = df_15m.iloc[-1]

                    # --- شروط الدخول الاحترافية ---
                    # 1. انضغاط (Width < 1.2%)
                    # 2. زخم صاعد (RSI 55-65)
                    # 3. سيولة داخلة (CMF > 0)
                    if last['Width'] < 1.2 and 55 <= last['RSI'] <= 65 and last['CMF'] > 0:
                        entry = last['c']
                        atr = last['ATR']
                        
                        # أهداف ديناميكية مجزأة
                        t1 = entry + (atr * 1.5) # هدف قريب لتأمين الصفقة
                        t2 = entry + (atr * 3)   # هدف متوسط
                        t3 = entry + (atr * 5)   # هدف الانفجار الكبير
                        stop = last['Lower']     # وقف الخسارة فني (تحت البولنجر)

                        msg = (
                            f"🌟 **فرصة انفجار عالي الجودة**\n"
                            f"العملة: #{symbol.replace('/USDT', '')}\n"
                            f"🕒 الفريم: 15m (مؤكد بـ 4h ✅)\n\n"
                            f"📊 **الضغط:** `{last['Width']:.2f}%` | **RSI:** `{last['RSI']:.1f}`\n"
                            f"💰 **تدفق الأموال (CMF):** `{last['CMF']:.2f}` (إيجابي)\n\n"
                            f"📥 **دخول:** `{entry:.4f}`\n"
                            f"🎯 **الهدف 1:** `{t1:.4f}`\n"
                            f"🎯 **الهدف 2:** `{t2:.4f}`\n"
                            f"🎯 **الهدف 3:** `{t3:.4f}`\n"
                            f"🛑 **الوقف:** `{stop:.4f}`"
                        )
                        send_to_all(msg)

    except Exception as e:
        print(f"Error: {e}")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_professional_pro, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def home():
    return "Professional V3: Multi-Timeframe & CMF Active!"

if __name__ == "__main__":
    scan_professional_pro()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
