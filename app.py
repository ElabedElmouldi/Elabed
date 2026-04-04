import os, requests, ccxt, time, json, logging
from datetime import datetime
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# --- إعدادات النظام والملفات ---
DATA_FILE = "ultimate_bot_v14_1.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- الإعدادات الشخصية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "-1003692815602"]

# إعدادات الاستراتيجية الاحترافية
BUFFER_PCT = 0.04        # ملاحقة السعر بمسافة 4% (مناسبة للسبوت والسوق الصاعد)
BE_TRIGGER = 7.0         # نقل الوقف لنقطة الدخول عند ربح 7%
PARTIAL_TP_PCT = 15.0    # بيع 50% من الكمية عند ربح 15%
MIN_VOLUME_LIMIT = 25_000_000 # الحد الأدنى للسيولة اليومية للعملة

# عداد المسح الساعي
total_scans_last_hour = 0

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"balance": 100.0, "active_trades": {}}

def save_db(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f)

# تحميل البيانات عند التشغيل
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
    except: return True

# --- إدارة الصفقات الذكية (v14.1) ---
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
                data['sl'] = data['entry_price'] * 1.01 
                data['is_secured'] = True
                send_telegram(f"🛡️ **تأمين صفقة**: {symbol}\nالربح وصل `{profit_pct:.1f}%`. الوقف الآن عند نقطة الدخول +1%.")

            # 2. جني ربح جزئي عند +15%
            if profit_pct >= PARTIAL_TP_PCT and not data.get('is_partial_tp', False):
                # بيع النصف بربح وإعادته للرصيد
                tp_usd = (data['invested_amount'] * 0.5) * (1 + profit_pct/100)
                CURRENT_BALANCE += tp_usd
                data['invested_amount'] *= 0.5 # النصف الآخر يكمل الملاحقة
                data['is_partial_tp'] = True
                send_telegram(f"💰 **جني أرباح جزئي (50%)**: {symbol}\nتم سحب الأرباح للمحفظة. النصف المتبقي يلاحق الموجة!")

            # 3. نظام الملاحقة بـ 4% (الزحف للأعلى)
            potential_sl = price * (1 - BUFFER_PCT)
            if potential_sl > data['sl']:
                data['sl'] = potential_sl

            # 4. الخروج النهائي عند ضرب الوقف
            if price <= data['sl']:
                final_pct = ((data['sl'] - data['entry_price']) / data['entry_price']) * 100
                final_total = data['invested_amount'] * (1 + final_pct/100)
                CURRENT_BALANCE += final_total
                
                icon = "💰" if final_pct > 0 else "🛑"
                send_telegram(f"{icon} **خروج نهائي**: {symbol}\nالنتيجة: `{final_pct:+.2f}%` \n🏦 الرصيد الإجمالي: `${CURRENT_BALANCE:.2f}`")
                to_remove.append(symbol)
                save_db({"balance": CURRENT_BALANCE, "active_trades": active_trades})

        for s in to_remove: del active_trades[s]
    except Exception as e: logger.error(f"Mgmt Error: {e}")

# --- رادار المسح لـ 100 عملة (v14.1) ---
def scan_for_signals():
    global total_scans_last_hour
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        check_trade_management()
        
        # حماية المحفظة: لا شراء إذا كان البيتكوين هابطاً
        if not is_market_safe(exchange): return

        tickers = exchange.fetch_tickers()
        # اختيار أفضل 100 عملة سيولة فوق 25 مليون دولار
        symbols = [s for s, d in tickers.items() if s.endswith('/USDT') and d.get('quoteVolume', 0) > MIN_VOLUME_LIMIT]
        symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:100]

        for symbol in symbols:
            total_scans_last_hour += 1
            if symbol in active_trades or len(active_trades) >= 5: continue
            time.sleep(0.15) # حماية API

            bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # فلتر سيولة الاختراق (1.5x المتوسط)
            avg_vol = df['v'].rolling(20).mean().iloc[-2]
            if df['v'].iloc[-1] < avg_vol * 1.5: continue

            # حساب البولينجر و RSI
            df['ma20'] = df['c'].rolling(20).mean()
            df['std'] = df['c'].rolling(20).std()
            df['upper'] = df['ma20'] + (df['std'] * 2)
            df['bw'] = (df['upper'] - (df['ma20'] - (df['std'] * 2))) / df['ma20']
            
            last = df.iloc[-1]
            # شروط الانفجار الصارمة
            if last['bw'] < 0.022 and last['c'] > last['upper']:
                # حساب RSI سريع
                delta = df['c'].diff(); g = (delta.where(delta > 0, 0)).rolling(14).mean(); l = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
                
                if 58 < rsi < 75:
                    trade_size = CURRENT_BALANCE * 0.20 # دخول بـ 20% لكل صفقة
                    active_trades[symbol] = {
                        'entry_price': last['c'],
                        'sl': last['c'] * (1 - BUFFER_PCT),
                        'invested_amount': trade_size,
                        'is_secured': False, 'is_partial_tp': False
                    }
                    save_db({"balance": CURRENT_BALANCE, "active_trades": active_trades})
                    send_telegram(f"🚀 **قنص انفجار (v14.1)**\n🪙 #{symbol}\n📈 السيولة: `قوية ✅` | النطاق: `ضيق جداً ✅` \n🛡️ الوقف الملاحق: `4%` | الرصيد المخصص: `${trade_size:.2f}`")
    except Exception as e: logger.error(f"Scan Error: {e}")

# --- نظام التقارير الساعية ---
def send_hourly_report():
    global total_scans_last_hour, CURRENT_BALANCE
    now = datetime.now().strftime("%H:%M")
    
    if not active_trades:
        msg = (f"🔍 **نبض الرادار ({now})**\n━━━━━━━━━━━━━━\n"
               f"✅ البوت يعمل ويبحث عن فرص.\n"
               f"📡 تم فحص `{total_scans_last_hour}` عملة في الساعة الأخيرة.\n"
               f"⚠️ الحالة: انتظار انفجار سعري يطابق الشروط.\n"
               f"💰 الرصيد المتوفر: `${CURRENT_BALANCE:.2f}`")
    else:
        msg = f"📊 **متابعة الصفقات ({now})**\n━━━━━━━━━━━━━━\n"
        for s, data in active_trades.items():
            try:
                curr_p = ccxt.binance().fetch_ticker(s)['last']
                p_pct = ((curr_p - data['entry_price']) / data['entry_price']) * 100
                msg += f"🪙 {s}: `{p_pct:+.2f}%` \n"
            except: pass
        msg += f"━━━━━━━━━━━━━━\n🏦 إجمالي المحفظة: `${CURRENT_BALANCE:.2f}`"

    send_telegram(msg)
    total_scans_last_hour = 0

# --- تشغيل المجدول ---
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_for_signals, 'interval', minutes=2)
scheduler.add_job(send_hourly_report, 'interval', hours=1)
scheduler.start()

@app.route('/')
def home(): return f"v14.1 Active - Scanned symbols: 100 - Balance: ${CURRENT_BALANCE:.2f}"

if __name__ == "__main__":
    send_telegram(f"💎 **إطلاق النسخة v14.1 الملكية**\nنطاق المسح: `100 عملة` | الحماية: `نشطة`\nبانتظار أول صيد ثقيل! 🦅")
    scan_for_signals()
    app.run(host='0.0.0.0', port=10000)
