import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام ---
DATA_FILE = "swing_bot_data.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f: return json.load(f)
    return {"balance": 100.0, "active_trades": {}, "daily_history": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

db = load_data()
CURRENT_BALANCE = db["balance"]
active_trades = db["active_trades"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- محرك المؤشرات الفنية ---
def calculate_indicators(df):
    df['sma200'] = df['c'].rolling(window=200).mean()
    df['ema9'] = df['c'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['c'].ewm(span=21, adjust=False).mean()
    df['ma20'] = df['c'].rolling(20).mean()
    df['std'] = df['c'].rolling(20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']
    
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

# --- إدارة صفقات السوينج (ملاحقة 3%) ---
def check_swing_logic():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(active_trades.items()):
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # ملاحقة السعر بمسافة 3% (مناسبة للسوينج)
            potential_sl = price * 0.97 
            
            if potential_sl > data['sl']:
                data['sl'] = potential_sl
                current_profit = ((price - data['entry_price']) / data['entry_price']) * 100
                # إشعار عند كل 5% ربح إضافي محقق
                if int(current_profit / 5) > data.get('last_milestone', 0):
                    data['last_milestone'] = int(current_profit / 5)
                    send_telegram(f"🔥 **تطور موجة السوينج**: {symbol}\nالربح اللحظي: `+{current_profit:.1f}%` \nالوقف المحجز: `{(data['sl']-data['entry_price'])/data['entry_price']*100:+.1f}%`")

            if price <= data['sl']:
                final_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                profit_usd = data['invested_amount'] * (final_pct / 100)
                CURRENT_BALANCE += profit_usd
                send_telegram(f"💰 **انتهاء الموجة**: {symbol}\nالربح الصافي: `{final_pct:+.2f}%` (${profit_usd:+.2f})\n🏦 الرصيد: `${CURRENT_BALANCE:.2f}`")
                to_remove.append(symbol)
                save_data({"balance": CURRENT_BALANCE, "active_trades": active_trades})
                
        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Swing Logic Error: {e}")

# --- رادار انفجار السوينج ---
def scan_for_swing_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_swing_logic()
        
        tickers = exchange.fetch_tickers()
        # اختيار العملات القوية جداً (سيولة > 40 مليون دولار)
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > 40_000_000]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]

        for symbol in symbols:
            if symbol in active_trades or len(active_trades) >= 5: continue
            time.sleep(0.2)

            # 1. تأكيد الاتجاه الكلي (4 ساعات)
            bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=210)
            df_4h = pd.DataFrame(bars_4h, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            if df_4h['c'].iloc[-1] < df_4h['c'].rolling(200).mean().iloc[-1]: continue

            # 2. فحص الانفجار (15 دقيقة)
            bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df_15m = calculate_indicators(pd.DataFrame(bars_15m, columns=['ts', 'o', 'h', 'l', 'c', 'v']))
            last = df_15m.iloc[-1]

            # شروط انفجار السوينج: ضيق شديد + اختراق فوليوم + RSI ممتاز
            if last['bw'] < 0.02 and last['c'] > last['upper'] and 60 < last['rsi'] < 75:
                trade_size = CURRENT_BALANCE * 0.20
                active_trades[symbol] = {
                    'entry_price': last['c'],
                    'sl': last['c'] * 0.96, # وقف خسارة أولي 4% (لتحمل تذبذب البداية)
                    'invested_amount': trade_size,
                    'last_milestone': 0
                }
                save_data({"balance": CURRENT_BALANCE, "active_trades": active_trades})
                send_telegram(f"🚀 **انفجار سوينج مكتشف!**\n🪙 #{symbol}\n📏 ضيق البولينجر: `{last['bw']*100:.1f}%` \n📈 الهدف: ركوب الموجة لأقصى مدى!")
    except Exception as e: logger.error(f"Swing Scan Error: {e}")

# --- المجدول والتشغيل ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_swing_signals, 'interval', minutes=2) # السوينج لا يحتاج مسح كل دقيقة
scheduler.start()

@app.route('/')
def home(): return f"Swing Bot v13.0 Active - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram(f"🦅 **رادار السوينج v13.0 قيد التشغيل**\nنظام صيد الموجات الكبرى نشط.")
    scan_for_swing_signals()
    app.run(host='0.0.0.0', port=10000)
