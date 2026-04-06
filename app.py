import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية (نظام 10 صفقات × 100$) ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
TAKE_PROFIT_PCT = 0.05  # هدف الربح 5%
STOP_LOSS_PCT = 0.04    # وقف الخسارة 4%

# استبعاد العملات الكبيرة والمستقرة لتركيز البحث على "الانفجارات"
STABLE_AND_BIG = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'LTC/USDT', 'ADA/USDT',
    'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'USDE/USDT', 'PYUSD/USDT', 'EUR/USDT'
]

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
closed_today = []
scan_index = 0
last_1h_report = datetime.now()
last_4h_report = datetime.now()

# --- 3. خوارزمية الـ 10 شروط الذهبية (v10 Logic) ---

def analyze_explosion_v10(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        close = df['c']
        
        # المتوسطات والبولنجر
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        std = close.rolling(20).std()
        upper_band = ema20 + (std * 2)
        bb_width = (upper_band - (ema20 - (std * 2))) / ema20
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))

        score = 0
        # [1-2] شروط السيولة (4 نقاط)
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 2

        # [3-5] شروط الزخم (3 نقاط)
        if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]: score += 1
        if (close.iloc[-1] - df['l'].iloc[-1]) / (df['h'].iloc[-1] - df['l'].iloc[-1] + 1e-9) > 0.8: score += 1
        if 55 < rsi.iloc[-1] < 75: score += 1

        # [6-8] شروط الانفجار الفني (3 نقاط)
        if close.iloc[-1] > upper_band.iloc[-1]: score += 1
        if bb_width.iloc[-5:].mean() < 0.03: score += 1 # ضيق النطاق (Squeeze)
        if close.iloc[-1] > df['h'].iloc[-11:-1].max(): score += 1 # اختراق قمة محلية

        # [9-10] فلاتر الحماية (إلزامية)
        price_change_1h = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4]
        if price_change_1h > 0.08: return None # تجنب العملات التي طارت فعلياً
        if close.iloc[-1] < df['o'].iloc[-1] * 1.01: return None # يجب أن تكون الشمعة صاعدة 1%

        return score if score >= 7 else None
    except: return None

# --- 4. نظام المسح الدوّار والتقارير ---

def get_filtered_symbols():
    try:
        tickers = exchange.fetch_tickers()
        filtered = [s for s in tickers.keys() if '/USDT' in s and s not in STABLE_AND_BIG and 'USD' not in s.split('/')[0]]
        return sorted(filtered, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:600]
    except: return []

def run_cyclic_scan_600():
    global scan_index, active_trades
    all_symbols = get_filtered_symbols()
    if not all_symbols: return
    
    start, end = scan_index * 150, (scan_index + 1) * 150
    current_group = all_symbols[start:end]
    radar_list = []

    for s in current_group:
        score = analyze_explosion_v10(s)
        if score:
            radar_list.append((s, score))
            if score >= 8 and len(active_trades) < MAX_TRADES and s not in active_trades:
                price = exchange.fetch_ticker(s)['last']
                active_trades[s] = {'entry': price, 'time': datetime.now()}
                send_telegram(f"🎯 *دخول آلي (v12.8):* `{s}`\n💵 السعر: `{price}`\n🚀 القوة: `{score}/10`")

    # تقرير الرادار (كل 15 دقيقة)
    msg = f"🛰️ *رادار الانفجار (المجموعة {scan_index+1}/4)*\n"
    if radar_list:
        radar_list.sort(key=lambda x: x[1], reverse=True)
        for s, sc in radar_list[:8]: msg += f"🔥 `{s}` | قوة: `{sc}/10` \n"
    else: msg += "_لا توجد انفجارات وشيكة في هذه المجموعة._"
    send_telegram(msg)
    
    scan_index = (scan_index + 1) % 4

def send_hourly_report():
    """ تقرير الصفقات المفتوحة ورادار الانفجار كل ساعة """
    open_msg = "📂 *الصفقات المفتوحة:* \n"
    if active_trades:
        for s, d in active_trades.items():
            cp = exchange.fetch_ticker(s)['last']
            pnl = (cp - d['entry']) / d['entry'] * 100
            open_msg += f"🔹 `{s}` | الربح: `{pnl:+.2f}%` \n"
    else: open_msg += "_لا توجد صفقات حالياً_\n"
    send_telegram(f"🕒 *تقرير الساعة القناص*\n━━━━━━━━━━━━━━\n{open_msg}")

def send_daily_summary():
    """ تقرير كل 4 ساعات بالصفقات المغلقة اليوم """
    global closed_today
    msg = "📋 *سجل الإغلاقات (4h Update)*\n━━━━━━━━━━━━━━\n"
    if closed_today:
        total_pnl = 0
        for t in closed_today:
            msg += f"{'✅' if t['pnl']>0 else '🛑'} `{t['symbol']}`: `{t['pnl']:+.2f}%` \n"
            total_pnl += (TRADE_AMOUNT * t['pnl'] / 100)
        msg += f"━━━━━━━━━━━━━━\n💰 إجمالي أرباح اليوم: `{total_pnl:+.2f}$`"
    else: msg += "_لا توجد إغلاقات اليوم بعد_"
    send_telegram(msg)

# --- 5. المحرك التنفيذي الرئيسي ---

def main_engine():
    global last_1h_report, last_4h_report, closed_today
    send_telegram("🦾 *v12.8 Sniper Global Deployed*\n- فحص 600 عملة (دورة 15 دقيقة)\n- هدف الربح: 5% | الوقف: 4%")

    last_scan = datetime.now() - timedelta(minutes=16)

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة الإغلاق (كل 15 ثانية)
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                pnl = (ticker['last'] - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                
                reason = ""
                if pnl >= TAKE_PROFIT_PCT: reason = "🎯 هدف (5%)"
                elif pnl <= -STOP_LOSS_PCT: reason = "🛑 وقف (4%)"

                if reason:
                    closed_today.append({'symbol': symbol, 'pnl': pnl*100})
                    del active_trades[symbol]
                    # تقرير فوري عند الإغلاق
                    balance = exchange.fetch_balance()
                    send_telegram(f"{reason}: `{symbol}`\n💰 متاح: `{balance['free']['USDT']:.2f}$`")

            # ب. تشغيل المسح الدوّار كل 15 دقيقة
            if now >= last_scan + timedelta(minutes=15):
                run_cyclic_scan_600()
                last_scan = now

            # ج. التقارير المجدولة
            if now >= last_1h_report + timedelta(hours=1):
                send_hourly_report()
                last_1h_report = now

            if now >= last_4h_report + timedelta(hours=4):
                send_daily_summary()
                last_4h_report = now

            if now.hour == 0 and now.minute <= 1: closed_today = [] # تصفير يومي

            time.sleep(15)
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Sniper v12.8 Active"
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
