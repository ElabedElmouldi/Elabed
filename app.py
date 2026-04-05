import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام للمجموعة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram_to_all(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"⚠️ خطأ إرسال: {e}")

# --- 2. خادم الويب (Keep-Alive) ---
app = Flask('')
@app.route('/')
def home(): return f"🚀 Bot Status: Active - {datetime.now().strftime('%H:%M:%S')}"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 3. إعدادات محرك التداول ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 100.0
PERCENT_PER_TRADE = 0.20
MAX_TRADES = 5
TARGET_PROFIT = 1.04
STOP_LOSS = 0.98
MIN_VOLUME = 10000000

active_trades = []
daily_closed_trades = []

def get_top_gainers():
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT', 'DAI/USDT']
        for s, d in tickers.items():
            if '/USDT' in s and s not in exclude and d['quoteVolume'] > MIN_VOLUME:
                gainers.append({'symbol': s, 'percentage': d['percentage']})
        gainers.sort(key=lambda x: x['percentage'], reverse=True)
        return [item['symbol'] for item in gainers[:100]]
    except: return []

def get_indicators(symbol):
    try:
        time.sleep(0.1)
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        df['ma'] = df['close'].rolling(window=20).mean()
        return df.iloc[-1]
    except: return None

# --- 4. وظائف التقارير الذكية ---

def send_open_trades_report():
    """تقرير الصفقات المفتوحة - يُرسل كل ساعتين"""
    if not active_trades:
        send_telegram_to_all("🔍 *تقرير الصفقات:* \nلا توجد صفقات مفتوحة حالياً، البوت في وضع الاستعداد.")
        return
    
    report = "📋 *تقرير الصفقات المفتوحة حالياً* \n\n"
    tickers = exchange.fetch_tickers()
    for t in active_trades:
        curr = tickers[t['symbol']]['last']
        pnl = ((curr - t['entry_price']) / t['entry_price']) * 100
        secured = "✅ نعم" if pnl >= 1.5 else "❌ لا"
        report += f"🪙 `{t['symbol']}` | الربح: `{pnl:+.2f}%` \n🛡️ تأمين: {secured} | القيمة: `{t['cost']:.2f}$` \n\n"
    send_telegram_to_all(report)

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_daily_report = datetime.now().date()
    last_2h_report = datetime.now()
    last_1h_heartbeat = datetime.now() # مؤقت إشعار الساعة

    send_telegram_to_all("🟢 *تم تشغيل البوت بنجاح!* \nسأرسل إشعاراً كل ساعة لتأكيد العمل.")

    while True:
        try:
            now = datetime.now()

            # 1. إشعار "البوت يعمل" كل ساعة (Heartbeat)
            if now >= last_1h_heartbeat + timedelta(hours=1):
                msg = f"📡 *إشعار روتيني:* \nالبوت يعمل بنجاح ويقوم بمسح السوق الآن.. \n⏰ الوقت: `{now.strftime('%H:%M')}`"
                send_telegram_to_all(msg)
                last_1h_heartbeat = now

            # 2. تقرير الصفقات المفتوحة كل ساعتين
            if now >= last_2h_report + timedelta(hours=2):
                send_open_trades_report()
                last_2h_report = now

            # 3. منطق البحث والدخول في الصفقات
            symbols = get_top_gainers()
            if len(active_trades) < MAX_TRADES:
                entry_amount = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    data = get_indicators(symbol)
                    if data is not None and data['rsi'] <= 45 and data['close'] <= data['ma']:
                        new_trade = {
                            'symbol': symbol, 'entry_price': data['close'],
                            'target': data['close'] * TARGET_PROFIT,
                            'stop': data['close'] * STOP_LOSS,
                            'cost': entry_amount, 'open_time': datetime.now()
                        }
                        active_trades.append(new_trade)
                        VIRTUAL_BALANCE -= entry_amount
                        send_telegram_to_all(f"🔔 *دخول صفقة:* `{symbol}` بسعر `{data['close']:.4f}`")

            # 4. مراقبة الإغلاق
            if active_trades:
                tickers = exchange.fetch_tickers()
                for trade in active_trades[:]:
                    p_now = tickers[trade['symbol']]['last']
                    if p_now >= trade['target'] or p_now <= trade['stop']:
                        is_win = p_now >= trade['target']
                        profit = trade['cost'] * (TARGET_PROFIT - 1) if is_win else -(trade['cost'] * (1 - STOP_LOSS))
                        VIRTUAL_BALANCE += (trade['cost'] + profit)
                        
                        icon = "✅" if is_win else "🛑"
                        send_telegram_to_all(f"{icon} *إغلاق صفقة:* `{trade['symbol']}` \nالربح: `{profit:+.2f}$` \nالرصيد: `{VIRTUAL_BALANCE:.2f}$`")
                        active_trades.remove(trade)

            time.sleep(45)
        except Exception as e:
            print(f"⚠️ خطأ: {e}"); time.sleep(20)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    run_trading_logic()
