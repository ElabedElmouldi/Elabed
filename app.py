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
def home(): return "🚀 Bot is Active!"

def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- 3. إعدادات البوت ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 100.0
PERCENT_PER_TRADE = 0.20
MAX_TRADES = 5
TARGET_PROFIT = 1.04
STOP_LOSS = 0.98

active_trades = []
daily_closed_trades = []

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

def send_open_trades_report():
    """تقرير الصفقات المفتوحة كل ساعتين"""
    if not active_trades:
        send_telegram_to_all("🔍 *تقرير الصفقات المفتوحة:* \nلا توجد صفقات مفتوحة حالياً.")
        return

    report = "📋 *تقرير الصفقات المفتوحة (كل ساعتين)* \n\n"
    tickers = exchange.fetch_tickers()
    
    for t in active_trades:
        current_price = tickers[t['symbol']]['last']
        pnl_perc = ((current_price - t['entry_price']) / t['entry_price']) * 100
        # نعتبر الصفقة مؤمنة إذا ارتفعت أكثر من 1.5% من سعر الدخول
        is_secured = "✅ نعم" if pnl_perc >= 1.5 else "❌ لا"
        
        report += f"🪙 *العملة:* `{t['symbol']}` \n"
        report += f"💰 *القيمة:* `{t['cost']:.2f}$` \n"
        report += f"⏰ *الدخول:* `{t['open_time'].strftime('%H:%M')}` \n"
        report += f"💵 *سعر الدخول:* `{t['entry_price']:.4f}` \n"
        report += f"📈 *النتيجة العائمة:* `{pnl_perc:+.2f}%` \n"
        report += f"🛡️ *تأمين الصفقة:* {is_secured} \n"
        report += f"--- \n"
    
    send_telegram_to_all(report)

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_daily_report = datetime.now().date()
    last_2h_report = datetime.now()

    send_telegram_to_all("🟢 *انطلق البوت!* \nتقرير دوري كل ساعتين + تقرير يومي عند الإغلاق.")

    while True:
        try:
            now = datetime.now()

            # 1. إرسال تقرير الصفقات المفتوحة كل ساعتين
            if now >= last_2h_report + timedelta(hours=2):
                send_open_trades_report()
                last_2h_report = now

            # 2. جلب العملات والبحث عن دخول
            symbols = [s for s, d in exchange.fetch_tickers().items() if '/USDT' in s and d['quoteVolume'] > 10000000]
            # (نفس منطق الفلترة لـ Top 100 Gainers هنا...)

            if len(active_trades) < MAX_TRADES:
                entry_amount = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                # ... (كود البحث عن دخول RSI + Bollinger) ...
                # ملاحظة: تأكد من إضافة 'open_time': datetime.now() عند تعريف أي صفقة جديدة

            # 3. مراقبة الإغلاق
            if active_trades:
                tickers = exchange.fetch_tickers()
                for trade in active_trades[:]:
                    p_now = tickers[trade['symbol']]['last']
                    if p_now >= trade['target'] or p_now <= trade['stop']:
                        # ... (كود الإغلاق وحفظ البيانات للتقرير اليومي) ...
                        active_trades.remove(trade)

            time.sleep(45)
        except Exception as e:
            print(f"⚠️ خطأ: {e}"); time.sleep(20)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    run_trading_logic()
