import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# --- 2. خادم الويب (Keep-Alive لمنصة Render) ---
app = Flask('')

@app.route('/')
def home():
    return f"🚀 Bot is Online | {datetime.now().strftime('%H:%M:%S')}"

def run_web_server():
    # Render يتطلب الاستماع للمنفذ الممرر في بيئة التشغيل PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 3. إعدادات الاستراتيجية (محفظة 500$) ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 500.0   # رأس المال المبدئي
PERCENT_PER_TRADE = 0.20  # الدخول بـ 20% من الرصيد المتاح (5 خانات)
MAX_TRADES = 5
TARGET_PROFIT = 1.04      # هدف 4%
STOP_LOSS = 0.98          # وقف 2%
SECURE_PROFIT_TRIGGER = 1.02 # تأمين عند ربح 2%
TIME_EXIT_HOURS = 12      # تدوير الرصيد بعد 12 ساعة

active_trades = []
daily_closed_trades = []

# --- 4. وظائف التحليل ---

def get_market_data():
    """جلب أفضل 250 عملة لضمان توفر الفرص ودوران السيولة"""
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT', 'DAI/USDT']
        for s, d in tickers.items():
            if '/USDT' in s and s not in exclude and d['quoteVolume'] > 5000000:
                gainers.append({'symbol': s, 'vol': d['quoteVolume']})
        gainers.sort(key=lambda x: x['vol'], reverse=True)
        return [item['symbol'] for item in gainers[:250]]
    except: return []

def get_indicators(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        df['ma20'] = df['c'].rolling(20).mean()
        df['vol_ma'] = df['v'].rolling(10).mean()
        return df.iloc[-1]
    except: return None

# --- 5. المنطق الرئيسي للتداول ---

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_1h = datetime.now()
    last_daily = datetime.now().date()

    print("✅ Trading logic started...")
    send_telegram("🟢 *تم تشغيل البوت بنجاح!* \nإجمالي المحفظة: `500$` \nجاهز لاقتناص الفرص..")

    while True:
        try:
            now = datetime.now()

            # إشعار "نبض البوت" كل ساعة
            if now >= last_1h + timedelta(hours=1):
                send_telegram(f"📡 *إشعار:* البوت يعمل ويبحث.. \nالرصيد الكلي: `{VIRTUAL_BALANCE + sum([t['cost'] for t in active_trades]):.2f}$` \nالمفتوح حالياً: `{len(active_trades)}` صفقات")
                last_1h = now

            # البحث عن صفقات جديدة (إذا توفرت خانات رصيد)
            if len(active_trades) < MAX_TRADES:
                symbols = get_market_data()
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    data = get_indicators(symbol)
                    if data is not None:
                        # شروط الدخول (RSI هادئ + سعر تحت المتوسط + فوليوم متصاعد)
                        if data['rsi'] <= 45 and data['c'] <= data['ma20'] and data['v'] > data['vol_ma']:
                            entry_amount = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                            
                            # خصم من الرصيد وتخزين الصفقة
                            VIRTUAL_BALANCE -= entry_amount
                            
                            new_trade = {
                                'symbol': symbol, 'entry_price': data['c'], 'cost': entry_amount,
                                'target': data['c'] * TARGET_PROFIT, 'stop': data['c'] * STOP_LOSS,
                                'open_time': now, 'is_secured': False
                            }
                            active_trades.append(new_trade)
                            
                            # رسالة الشراء المطلوبة
                            msg = (f"🔔 *فتح صفقة جديدة*\n"
                                   f"🪙 العملة: `{symbol}`\n"
                                   f"💰 قيمة الصفقة: `{entry_amount:.2f}$`\n"
                                   f"💵 سعر الدخول: `{data['c']:.4f}`\n"
                                   f"⏰ وقت الدخول: `{now.strftime('%H:%M:%S')}`\n"
                                   f"📉 *الرصيد المتبقي في المحفظة:* `{VIRTUAL_BALANCE:.2f}$` ✅")
                            send_telegram(msg)

            # مراقبة وإدارة الصفقات المفتوحة
            if active_trades:
                tickers = exchange.fetch_tickers()
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    pnl_ratio = (p_now / t['entry_price'])
                    
                    # 1. الخروج الزمني بعد 12 ساعة لتدوير السيولة
                    if now >= t['open_time'] + timedelta(hours=TIME_EXIT_HOURS):
                        VIRTUAL_BALANCE += t['cost'] * pnl_ratio
                        active_trades.remove(t)
                        send_telegram(f"⏱️ *خروج زمني:* `{t['symbol']}` لتحرير السيولة.")
                        continue

                    # 2. تأمين الربح (Break-even) عند وصول الربح لـ 2%
                    if pnl_ratio >= SECURE_PROFIT_TRIGGER and not t['is_secured']:
                        t['stop'] = t['entry_price']
                        t['is_secured'] = True
                        send_telegram(f"🛡️ *تأمين:* `{t['symbol']}` (تم رفع الوقف لسعر الدخول)")

                    # 3. الإغلاق النهائي (الهدف 4% أو الوقف 2%)
                    if p_now >= t['target'] or p_now <= t['stop']:
                        profit_usdt = t['cost'] * (pnl_ratio - 1)
                        VIRTUAL_BALANCE += (t['cost'] + profit_usdt)
                        
                        icon = "✨" if profit_usdt > 0 else "🛑"
                        send_telegram(f"{icon} *إغلاق صفقة:* `{t['symbol']}`\n"
                                      f"📈 الربح/الخسارة: `{profit_usdt:+.2f}$` \n"
                                      f"💰 إجمالي المحفظة: `{VIRTUAL_BALANCE:.2f}$`")
                        active_trades.remove(t)

            time.sleep(40) # تجنب الحظر من Binance API
        except Exception as e:
            print(f"Runtime Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    # تشغيل خادم الويب لضمان بقاء Render نشطاً
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    # تشغيل منطق التداول
    run_trading_logic()
