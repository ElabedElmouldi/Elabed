import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)

# ==========================================
# --- إعدادات التلجرام (يجب تعبئتها) ---
# ==========================================
TOKEN = "ضـع_تـوكن_البـوت_هـنا"
# ضع أرقام الـ ID الخاصة بك وبأصدقائك هنا (مثال: ["12345678", "87654321"])
FRIENDS_IDS = ["ضـع_الـID_الخاص_بك_هنا"] 

STABLE_COINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FDUSD', 'USDS', 'EUR', 'GBP']

def send_to_all(message):
    """إرسال الرسائل لجميع المشتركين في القائمة"""
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")

def send_welcome_message():
    """رسالة ترحيبية تعمل فور تشغيل الب)وت"""
    msg = (
        "🚀 **تم تشغيل رادار الانفجار السعري V4.2**\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ البوت متصل الآن بسيرفر Render.\n"
        "📡 جاري مراقبة السوق (فريم 15 دقيقة).\n"
        "🔍 تأكيد الاتجاه (فريم 4 ساعات).\n"
        "💰 فلتر الربح المتوقع: +5% فما فوق.\n"
        "━━━━━━━━━━━━━━━\n"
        "✨ سأرسل لك رسالة حالة كل ساعتين للتأكيد."
    )
    send_to_all(msg)

def send_heartbeat():
    """تأكيد أن البوت لا يزال يعمل"""
    now = datetime.now().strftime('%H:%M')
    msg = f"🤖 **تحديث الحالة:**\nأنا أعمل بنشاط وأراقب الصفقات الآن. (توقيت تونس: {now})"
    send_to_all(msg)

def get_data(exchange, symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    except:
        return pd.DataFrame()

def calculate_indicators(df):
    if df.empty: return df
    # 1. البولنجر باند
    df['MA20'] = df['c'].rolling(20).mean()
    df['STD'] = df['c'].rolling(20).std()
    df['Lower'] = df['MA20'] - (df['STD'] * 2)
    df['Width'] = (df['STD'] * 4) / df['MA20'] * 100

    # 2. RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    # 3. تدفق الأموال CMF
    mfv = ((df['c'] - df['l']) - (df['h'] - df['c'])) / (df['h'] - df['l'] + 1e-9) * df['v']
    df['CMF'] = mfv.rolling(20).sum() / (df['v'].rolling(20).sum() + 1e-9)

    # 4. مؤشر ATR للأهداف
    df['TR'] = np.maximum((df['h'] - df['l']), np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['ATR'] = df['TR'].rolling(14).mean()
    return df

def scan_market():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning market...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        # استبعاد العملات المستقرة والتركيز على USDT
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]

        for symbol in symbols:
            vol_24h = tickers[symbol]['quoteVolume']
            # فلتر السيولة المتوسطة (النطاق المتفجر)
            if 10_000_000 <= vol_24h <= 300_000_000:
                
                # تأكيد الاتجاه الصاعد على 4 ساعات
                df_4h = get_data(exchange, symbol, '4h', 50)
                if df_4h.empty: continue
                ema_50_4h = df_4h['c'].ewm(span=50, adjust=False).mean().iloc[-1]
                
                if df_4h['c'].iloc[-1] > ema_50_4h:
                    
                    # تحليل فريم 15 دقيقة
                    df_15m = get_data(exchange, symbol, '15m', 100)
                    df_15m = calculate_indicators(df_15m)
                    if df_15m.empty: continue
                    last = df_15m.iloc[-1]

                    # شروط الانفجار (ضغط حاد + RSI صاعد + سيولة داخلة)
                    if last['Width'] < 1.2 and 55 <= last['RSI'] <= 65 and last['CMF'] > 0:
                        entry = last['c']
                        target = entry + (last['ATR'] * 3) # الهدف
                        stop = last['Lower']              # الوقف

                        profit_pct = ((target - entry) / entry) * 100
                        loss_pct = ((entry - stop) / entry) * 100
                        
                        # فلتر: لا نرسل صفقات ربحها أقل من 5%
                        if profit_pct >= 5.0:
                            msg = (
                                f"🌋 **إشارة انفجار مؤكدة (+{profit_pct:.1f}%)**\n"
                                f"العملة: #{symbol.replace('/USDT', '')}\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📥 **نقطة الدخول:** `{entry:.4f}`\n"
                                f"🛑 **وقف الخسارة:** `{stop:.4f}` ({loss_pct:.1f}-%)\n"
                                f"🎯 **الهدف المتوقع:** `{target:.4f}` (+{profit_pct:.1f}%)\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📊 **التحليل الفني:**\n"
                                f"• RSI: `{last['RSI']:.1f}`\n"
                                f"• السيولة CMF: `{last['CMF']:.2f}`\n"
                                f"• حجم التداول: `${vol_24h/1e6:.1f}M`"
                            )
                            send_to_all(msg)
    except Exception as e:
        print(f"Scanner Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_market, 'interval', minutes=15)
scheduler.add_job(send_heartbeat, 'interval', hours=2)
scheduler.start()

@app.route('/')
def home():
    return "<h1>Robot V4.2 is Online and Scanning!</h1>"

if __name__ == "__main__":
    # 1. إرسال رسالة ترحيبية عند الإقلاع
    send_welcome_message()
    
    # 2. تشغيل أول فحص فوراً
    scan_market()
    
    # 3. تشغيل سيرفر الويب (Render)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
