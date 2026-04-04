import os, requests, ccxt, time, json, logging
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام ---
DATA_FILE = "ultimate_bot_v14.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الاستراتيجية المتقدمة
BUFFER_PCT = 0.04       # ملاحقة 4%
BE_TRIGGER = 7.0        # تأمين عند 7% ربح
PARTIAL_TP_PCT = 15.0   # بيع نصف الكمية عند 15%

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f: return json.load(f)
    return {"balance": 100.0, "active_trades": {}}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

db = load_db()
CURRENT_BALANCE = db["balance"]
active_trades = db["active_trades"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- فلتر حماية البيتكوين (BTC Guard) ---
def is_market_safe(exchange):
    try:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='4h', limit=200)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        sma200 = df['c'].rolling(200).mean().iloc[-1]
        return df['c'].iloc[-1] > sma200
    except: return True # في حال الخطأ نستمر بحذر

# --- إدارة الصفقات الذكية (تأمين + جني جزئي) ---
def check_trade_management():
    global CURRENT_BALANCE
    try:
        exchange = ccxt.binance()
        to_remove = []
        for symbol, data in list(active_trades.items()):
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            profit_pct = ((price - data['entry_price']) / data['entry_price']) * 100
            
            # 1. تأمين الربح (Break-even) عند +7%
            if profit_pct >= BE_TRIGGER and not data.get('is_secured', False):
                data['sl'] = data['entry_price'] * 1.01 # نقل الوقف لربح 1%
                data['is_secured'] = True
                send_telegram(f"🛡️ **تأمين (BE)**: {symbol}\nالربح وصل {profit_pct:.1f}%. الوقف الآن عند نقطة الدخول.")

            # 2. جني ربح جزئي عند +15%
            if profit_pct >= PARTIAL_TP_PCT and not data.get('is_partial_tp', False):
                tp_amount = data['invested_amount'] * 0.5 * (1 + profit_pct/100)
                CURRENT_BALANCE += tp_amount
                data['invested_amount'] *= 0.5 # تقليل الكمية المتبقية للنصف
                data['is_partial_tp'] = True
                send_telegram(f"💰 **جني ربح جزئي (50%)**: {symbol}\nتم سحب الأرباح وبقاء النصف للملاحقة.")

            # 3. الملاحقة بـ 4%
            potential_sl = price * (1 - BUFFER_PCT)
            if potential_sl > data['sl']:
                data['sl'] = potential_sl

            # الخروج النهائي
            if price <= data['sl']:
                final_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                final_usd = data['invested_amount'] * (final_pct / 100)
                CURRENT_BALANCE += (data['invested_amount'] + final_usd)
                send_telegram(f"🛑 **خروج نهائي**: {symbol}\nالربح: `{final_pct:+.2f}%`\n🏦 الرصيد: `${CURRENT_BALANCE:.2f}`")
                to_remove.append(symbol)
                save_db({"balance": CURRENT_BALANCE, "active_trades": active_trades})

        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Mgmt Error: {e}")

# --- رادار الانفجار مع فلتر الفوليوم والبيتكوين ---
def scan_for_signals():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_trade_management()
        
        if not is_market_safe(exchange):
            return # توقف عن الشراء إذا كان البيتكوين هابطاً

        tickers = exchange.fetch_tickers()
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > 40_000_000]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]

        for symbol in symbols:
            if symbol in active_trades or len(active_trades) >= 5: continue
            time.sleep(0.2)

            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # فلتر الفوليوم (يجب أن يكون فوليوم الاختراق أعلى بـ 1.5 مرة من المتوسط)
            avg_vol = df['v'].rolling(20).mean().iloc[-2]
            current_vol = df['v'].iloc[-1]
            if current_vol < avg_vol * 1.5: continue

            # مؤشرات البولينجر و RSI
            df['ma20'] = df['c'].rolling(20).mean()
            df['std'] = df['c'].rolling(20).std()
            df['upper'] = df['ma20'] + (df['std'] * 2)
            df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']
            
            last = df.iloc[-1]
            if last['bw'] < 0.02 and last['c'] > last['upper'] and 60 < rsi_calc(df) < 75:
                trade_size = CURRENT_BALANCE * 0.20
                active_trades[symbol] = {
                    'entry_price': last['c'],
                    'sl': last['c'] * 0.96,
                    'invested_amount': trade_size,
                    'is_secured': False, 'is_partial_tp': False
                }
                save_db({"balance": CURRENT_BALANCE, "active_trades": active_trades})
                send_telegram(f"🚀 **انفجار مؤكد (v14)**\n🪙 #{symbol}\n📈 الفوليوم: `قوي ✅` | السوق: `آمن ✅`")
    except Exception as e: logger.error(f"Scan Error: {e}")

def rsi_calc(df):
    delta = df['c'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss))).iloc[-1]

# --- المجدول والتشغيل ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=2)
scheduler.start()

@app.route('/')
def home(): return f"Ultimate Bot v14 - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram(f"💎 **تشغيل النسخة المتكاملة v14.0**\nكل أنظمة الأمان (بيتكوين، فوليوم، تأمين، جني جزئي) نشطة.")
    scan_for_signals()
    app.run(host='0.0.0.0', port=10000)
