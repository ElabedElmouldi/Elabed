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

# --- 2. خادم الويب (تصحيح لمنصة Render) ---
app = Flask('')

@app.route('/')
def home():
    return f"🚀 Bot is Online | {datetime.now().strftime('%H:%M:%S')}"

def run_web_server():
    # Render يتطلب الاستماع للمنفذ الممرر في بيئة التشغيل
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 3. إعدادات الاستراتيجية ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 500.0   
PERCENT_PER_TRADE = 0.20 
MAX_TRADES = 5
TARGET_PROFIT = 1.04     
DYNAMIC_EXIT_RSI = 70    
SECURE_PROFIT_TRIGGER = 1.02 
STOP_LOSS = 0.98         
TIME_EXIT_HOURS = 12     

active_trades = []
daily_closed_trades = []

# --- 4. الدالات المساعدة ---

def get_market_data():
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT']
        for s, d in tickers.items():
            if '/USDT' in s and s not in exclude and d['quoteVolume'] > 5000000:
                gainers.append({'symbol': s, 'vol': d['quoteVolume']})
        gainers.sort(key=lambda x: x['vol'], reverse=True)
        return [item['symbol'] for item in gainers[:250]]
    except Exception as e:
        print(f"Market Data Error: {e}")
        return []

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

# --- 5. المنطق الرئيسي (مع حماية من الانهيار) ---

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_1h = datetime.now()
    last_2h = datetime.now()
    last_daily = datetime.now().date()

    print("✅ Trading logic started...")
    send_telegram("🟢 *تم إعادة تشغيل البوت بنجاح!* \nالرصيد: `500$`")

    while True:
        try:
            now = datetime.now()

            # تقارير الوقت
            if now >= last_1h + timedelta(hours=1):
                send_telegram(f"📡 *نبض البوت:* يعمل.. صفقات مفتوحة: `{len(active_trades)}`")
                last_1h = now

            if now >= last_2h + timedelta(hours=2):
                # دالة تقرير الساعتين (يمكنك إضافتها هنا)
                last_2h = now

            # البحث عن صفقات
            if len(active_trades) < MAX_TRADES:
                symbols = get_market_data()
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    data = get_indicators(symbol)
                    if data is not None:
                        if data['rsi'] <= 45 and data['c'] <= data['ma20'] and data['v'] > data['vol_ma']:
                            entry_amt = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                            new_trade = {
                                'symbol': symbol, 'entry_price': data['c'], 'cost': entry_amt,
                                'target': data['c'] * TARGET_PROFIT, 'stop': data['c'] * STOP_LOSS,
                                'open_time': now, 'is_secured': False
                            }
                            active_trades.append(new_trade)
                            VIRTUAL_BALANCE -= entry_amt
                            send_telegram(f"🔔 *شراء:* `{symbol}` بسعر `{data['c']:.4f}`")

            # إدارة الصفقات
            if active_trades:
                tickers = exchange.fetch_tickers()
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    pnl_pct = (p_now / t['entry_price'])
                    
                    # خروج زمني
                    if now >= t['open_time'] + timedelta(hours=TIME_EXIT_HOURS):
                        VIRTUAL_BALANCE += t['cost'] * pnl_pct
                        active_trades.remove(t)
                        send_telegram(f"⏱️ *خروج زمني:* `{t['symbol']}`")
                        continue

                    # تأمين الصفقة
                    if pnl_pct >= SECURE_PROFIT_TRIGGER and not t['is_secured']:
                        t['stop'] = t['entry_price']
                        t['is_secured'] = True
                        send_telegram(f"🛡️ *تأمين:* `{t['symbol']}` عند سعر الدخول.")

                    # إغلاق (هدف أو وقف)
                    if p_now >= t['target'] or p_now <= t['stop']:
                        profit = t['cost'] * (pnl_pct - 1)
                        VIRTUAL_BALANCE += (t['cost'] + profit)
                        daily_closed_trades.append({'symbol': t['symbol'], 'profit_usdt': profit, 'open_time': t['open_time'], 'close_time': now})
                        active_trades.remove(t)
                        send_telegram(f"{'✨' if profit > 0 else '🛑'} *إغلاق:* `{t['symbol']}` | `{profit:+.2f}$`")

            time.sleep(45)
        except Exception as e:
            print(f"Runtime Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    # تشغيل خادم الويب في خيط منفصل
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    # تشغيل منطق التداول في الخيط الرئيسي
    run_trading_logic()
