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

# --- 2. الإعدادات المالية والفلاتر ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
TAKE_PROFIT_PCT = 0.05
STOP_LOSS_PCT = 0.04

STABLE_AND_BIG = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT',
    'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'USDE/USDT', 'PYUSD/USDT'
]

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
closed_today = []
scan_index = 0
mega_scan_results = [] # مخزن لتجميع نتائج الـ 900 عملة
last_scan_time = datetime.now() - timedelta(minutes=6)

# --- 3. خوارزمية الـ 10 شروط الذهبية ---

def analyze_logic_v10(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        close = df['c']
        
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        std = close.rolling(20).std()
        upper_band = ema20 + (std * 2)
        bb_width = (upper_band - (ema20 - (std * 2))) / (ema20 + 1e-9)
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))

        score = 0
        # سيولة (4 نقاط)
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 2
        # زخم (3 نقاط)
        if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]: score += 1
        if (close.iloc[-1] - df['l'].iloc[-1]) / (df['h'].iloc[-1] - df['l'].iloc[-1] + 1e-9) > 0.8: score += 1
        if 55 < rsi.iloc[-1] < 75: score += 1
        # فني (3 نقاط)
        if close.iloc[-1] > upper_band.iloc[-1]: score += 1
        if bb_width.iloc[-5:].mean() < 0.03: score += 1
        if close.iloc[-1] > df['h'].iloc[-11:-1].max(): score += 1

        # فلاتر حماية
        price_change_1h = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4]
        if price_change_1h > 0.08: return None 
        if close.iloc[-1] < df['o'].iloc[-1] * 1.01: return None 

        return score if score >= 6 else None # نسجل أي عملة فوق 6 لنرتب التوب 20 لاحقاً
    except: return None

# --- 4. محرك المسح الضخم (900 عملة) ---

def get_900_symbols():
    try:
        tickers = exchange.fetch_tickers()
        filtered = [s for s in tickers.keys() if '/USDT' in s and s not in STABLE_AND_BIG and 'USD' not in s.split('/')[0]]
        # ترتيب حسب السيولة لجلب أنشط 900 عملة
        return sorted(filtered, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
    except: return []

def run_mega_scan():
    global scan_index, mega_scan_results, active_trades
    all_symbols = get_900_symbols()
    if not all_symbols: return
    
    # تحديد نطاق المجموعة (0-150, 150-300, ..., 750-900)
    start, end = scan_index * 150, (scan_index + 1) * 150
    current_group = all_symbols[start:end]
    
    for s in current_group:
        score = analyze_logic_v10(s)
        if score:
            mega_scan_results.append({'symbol': s, 'score': score})
            # فتح صفقة تلقائية إذا كانت الإشارة قوية جداً (9 أو 10)
            if score >= 9 and len(active_trades) < MAX_TRADES and s not in active_trades:
                price = exchange.fetch_ticker(s)['last']
                active_trades[s] = {'entry': price, 'time': datetime.now()}
                send_telegram(f"🚀 *دخول آلي قناص:* `{s}`\n💵 السعر: `{price}`\n🔥 القوة: `{score}/10`")

    # إرسال إشعار بإتمام مجموعة
    print(f"Finished group {scan_index + 1}/6")
    
    scan_index += 1
    
    # إذا اكتملت الـ 6 مجموعات (بعد 30 دقيقة)
    if scan_index >= 6:
        send_top_20_report()
        scan_index = 0
        mega_scan_results = [] # تصفير النتائج لبدء دورة جديدة

def send_top_20_report():
    """ إرسال قائمة أفضل 20 عملة من أصل 900 بعد كل دورة (30 دقيقة) """
    if not mega_scan_results:
        send_telegram("🛰️ *تقرير النصف ساعة:*\n_لم يتم العثور على فرص قوية في الـ 900 عملة الماضية._")
        return

    # ترتيب النتائج حسب الـ Score
    top_20 = sorted(mega_scan_results, key=lambda x: x['score'], reverse=True)[:20]
    
    report = "🏆 *قائمة النخبة (أفضل 20 عملة انفجارية)*\n"
    report += "🔍 تم مسح 900 عملة خلال الـ 30 دقيقة الماضية\n"
    report += "━━━━━━━━━━━━━━\n"
    for i, item in enumerate(top_20, 1):
        report += f"{i}. `{item['symbol']}` ➔ القوة: `{item['score']}/10` \n"
    
    send_telegram(report)

# --- 5. المحرك التنفيذي ---

def main_engine():
    global last_scan_time
    send_telegram("📡 *v13.0 Mega Scanner Active*\n- مسح 900 عملة (150 كل 5 دقائق)\n- تقرير التوب 20 كل نصف ساعة")

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة الصفقات المفتوحة للبيع
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                pnl = (ticker['last'] - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                if pnl >= TAKE_PROFIT_PCT or pnl <= -STOP_LOSS_PCT:
                    status = "✅ هدف (5%)" if pnl > 0 else "🛑 وقف (4%)"
                    send_telegram(f"{status}: `{symbol}`\nالربح: `{pnl*100:+.2f}%`")
                    del active_trades[symbol]

            # ب. تشغيل المسح كل 5 دقائق
            if now >= last_scan_time + timedelta(minutes=5):
                run_mega_scan()
                last_scan_time = now

            time.sleep(20)
        except Exception as e:
            time.sleep(30)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Mega Scanner v13.0"
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
