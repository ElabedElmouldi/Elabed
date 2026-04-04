import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام والملفات ---
DATA_FILE = "bot_data.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# --- وظائف حفظ واستعادة البيانات (الاستمرارية) ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"balance": 100.0, "active_trades": {}, "daily_history": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# تحميل البيانات عند التشغيل
db = load_data()
CURRENT_BALANCE = db["balance"]
active_trades = db["active_trades"]
daily_history = db["daily_history"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك المؤشرات الفنية المطور ---
def calculate_indicators(df):
    # المتوسطات
    df['sma200'] = df['c'].rolling(window=200).mean()
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    # البولينجر وضيق النطاق
    df['ma20'] = df['c'].rolling(20).mean()
    df['std'] = df['c'].rolling(20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']
    # RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

# --- محرك الملاحقة الذكية (تعديل 2% لتقليل الخروج المبكر) ---
def check_market_logic():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(active_trades.items()):
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # تحديث الوقف: يتبع السعر بفارق 2% لحماية الأرباح مع ترك مساحة تذبذب
            potential_sl = price * 0.98 
            
            if potential_sl > data['sl']:
                data['sl'] = potential_sl
                # إرسال تحديث عند كل زيادة 1% في الربح المحجوز
                current_sl_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                if int(current_sl_pct) > int(data.get('last_notified_sl', -1)):
                    data['last_notified_sl'] = int(current_sl_pct)
                    send_telegram(f"📈 **رفع الوقف**: {symbol}\nالربح المحجز حالياً: `+{current_sl_pct:.1f}%`")

            # تنفيذ الخروج
            if price <= data['sl']:
                final_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                profit_usd = data['invested_amount'] * (final_pct / 100)
                CURRENT_BALANCE += profit_usd
                daily_history.append({'symbol': symbol, 'profit': round(final_pct, 2), 'usd': profit_usd})
                
                # حفظ البيانات فوراً بعد الإغلاق
                save_data({"balance": CURRENT_BALANCE, "active_trades": active_trades, "daily_history": daily_history})
                
                send_telegram(f"💰 **إغلاق**: {symbol}\nالنتيجة: `{final_pct:+.2f}%` (${profit_usd:+.2f})\n🏦 الرصيد: `${CURRENT_BALANCE:.2f}`")
                to_remove.append(symbol)
                
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Logic Error: {e}")

# --- الرادار المطور (سيولة + تأكيد فريم الساعة) ---
def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_market_logic()
        
        tickers = exchange.fetch_tickers()
        # اختيار أفضل 50 عملة سيولة (أكثر من 20M$) لتجنب التلاعب
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > 20_000_000]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

        for symbol in symbols:
            if symbol in active_trades or len(active_trades) >= 5: continue
            
            # حماية الـ API من الحظر (Sleep)
            time.sleep(0.2) 
            
            # فحص فريم الساعة (التأكيد الكلي)
            h1_bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
            df_h1 = pd.DataFrame(h1_bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            if df_h1['c'].iloc[-1] < df_h1['c'].rolling(200).mean().iloc[-1]: continue # تجاهل لو الاتجاه العام هابط

            # فحص فريم الـ 15 دقيقة (نقطة الدخول)
            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=200)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df = calculate_indicators(df)
            last = df.iloc[-1]

            # شروط الدخول المتكاملة
            if last['bw'] < 0.03 and last['c'] > last['upper'] and last['ema9'] > last['ema21'] and 55 < last['rsi'] < 75:
                trade_size = CURRENT_BALANCE * 0.20 # 20% لكل صفقة
                
                active_trades[symbol] = {
                    'entry_price': last['c'],
                    'sl': last['c'] * 0.98, # وقف أولي 2%
                    'invested_amount': trade_size,
                    'last_notified_sl': -1
                }
                save_data({"balance": CURRENT_BALANCE, "active_trades": active_trades, "daily_history": daily_history})
                send_telegram(f"🎯 **دخول ذكي (v12.0)**\n🪙 #{symbol}\n📏 الضيق: `{last['bw']*100:.1f}%` | فريم الساعة: ✅\n🚀 نظام الملاحقة الذكية (2%) نشط!")
    except Exception as e: logger.error(f"Scan Error: {e}")

# --- التقارير ---
def send_daily_summary():
    global daily_history
    if not daily_history: return
    total_usd = sum([d['usd'] for d in daily_history])
    report = f"📅 **ملخص اليوم**\n━━━━━━━━━━━━━━\n✅ صفقات: `{len(daily_history)}` | أرباح: `${total_usd:+.2f}`\n🏦 رصيد المحفظة: `${CURRENT_BALANCE:.2f}`"
    send_telegram(report)
    daily_history = []
    save_data({"balance": CURRENT_BALANCE, "active_trades": active_trades, "daily_history": []})

# --- التشغيل ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=1)
scheduler.add_job(send_daily_summary, 'cron', hour=23, minute=55)
scheduler.start()

@app.route('/')
def home(): return f"Bot v12.0 Stable - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram(f"🚀 **تم تشغيل v12.0 بنظام حفظ البيانات**\nالرصيد المستعاد: `${CURRENT_BALANCE:.2f}`")
    scan_for_signals()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
