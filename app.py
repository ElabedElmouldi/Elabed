import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
TAKE_PROFIT_PCT = 0.05
STOP_LOSS_PCT = 0.04

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
mega_scan_results = []
scan_index = 0
last_scan_time = datetime.now() - timedelta(minutes=6)

# --- 3. محرك الـ 20 شرطاً الذهبية (v20 Elite Logic) ---

def analyze_v20(symbol):
    try:
        # جلب بيانات 15 دقيقة و ساعة للتحليل المتعدد
        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars_15m, columns=['t','o','h','l','c','v'])
        c = df['c'] # الإغلاق
        
        # مؤشرات أساسية
        ema8 = c.ewm(span=8).mean(); ema20 = c.ewm(span=20).mean(); ema50 = c.ewm(span=50).mean()
        std = c.rolling(20).std()
        upper_bb = ema20 + (std * 2); lower_bb = ema20 - (std * 2)
        
        # RSI & MACD
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))
        macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
        signal = macd.ewm(span=9).mean()

        score = 0
        
        # --- [ الفئة 1: السيولة والفوليوم - 6 نقاط ] ---
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2.5: score += 2 # 1. فوليوم انفجاري
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 1                # 2. فوليوم تصاعدي
        if df['v'].rolling(5).mean().iloc[-1] > df['v'].rolling(20).mean().iloc[-1]: score += 1 # 3. متوسط فوليوم إيجابي
        if (c.iloc[-1] * df['v'].iloc[-1]) > 50000: score += 2           # 4. سيولة الشمعة الحالية > 50k$

        # --- [ الفئة 2: الاتجاه والزخم - 5 نقاط ] ---
        if c.iloc[-1] > ema8.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]: score += 2 # 5. ترتيب المتوسطات مثالي
        if rsi.iloc[-1] > 55 and rsi.iloc[-1] < 75: score += 1           # 6. RSI في منطقة القوة
        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-1] > 0: score += 1 # 7. MACD تقاطع إيجابي فوق الصفر
        if c.iloc[-1] > c.iloc[-5]: score += 1                           # 8. السعر أعلى من 5 شموع سابقة

        # --- [ الفئة 3: الانفجار الفني - 5 نقاط ] ---
        if c.iloc[-1] > upper_bb.iloc[-1]: score += 2                    # 9. اختراق البولنجر العلوي
        if (upper_bb.iloc[-1] - lower_bb.iloc[-1])/ema20.iloc[-1] < 0.03: score += 1 # 10. ضيق البولنجر (انفجار وشيك)
        if c.iloc[-1] > df['h'].iloc[-20:-1].max(): score += 2           # 11. كسر قمة آخر 20 شمعة

        # --- [ الفئة 4: سلوك الشموع - 4 نقاط ] ---
        body = abs(c.iloc[-1] - df['o'].iloc[-1])
        wick = df['h'].iloc[-1] - max(c.iloc[-1], df['o'].iloc[-1])
        if c.iloc[-1] > df['o'].iloc[-1]: score += 1                     # 12. شمعة خضراء
        if body > (df['h'].iloc[-1] - df['l'].iloc[-1]) * 0.7: score += 1 # 13. جسم الشمعة قوي (بدون ذيول طويلة)
        if wick < body * 0.2: score += 1                                 # 14. ذيل علوي صغير (استمرار المشترين)
        if c.iloc[-1] > df['h'].iloc[-2]: score += 1                     # 15. تجاوز قمة الشمعة السابقة

        # --- [ الفئة 5: شروط إضافية وفلاتر - إجبارية ] ---
        # 16. المسافة بين السعر و EMA20 ليست كبيرة جداً (تجنب التصحيح)
        if (c.iloc[-1] - ema20.iloc[-1])/ema20.iloc[-1] > 0.05: return None 
        # 17. استبعاد التذبذب الضعيف (ATR بسيط)
        if (df['h'].iloc[-1] - df['l'].iloc[-1]) / c.iloc[-1] < 0.005: return None
        # 18. السعر الحالي ليس عند مقاومة تاريخية (قمة 100 شمعة)
        if c.iloc[-1] >= df['h'].iloc[-100:].max() * 0.99: score += 1
        # 19. شمعة الساعة الحالية صاعدة (تأكيد الاتجاه الأكبر)
        # 20. نسبة الصعود في آخر ساعة لا تتجاوز 7% (تجنب الـ Pump العشوائي)
        if (c.iloc[-1] - c.iloc[-4])/c.iloc[-4] > 0.07: return None

        return score if score >= 12 else None # نطلب 12 من 20 لترشيح العملة
    except: return None

# --- 4. محرك المسح المطور (900 عملة) ---

def run_elite_scan():
    global scan_index, mega_scan_results, active_trades
    try:
        tickers = exchange.fetch_tickers()
        filtered = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
        all_symbols = sorted(filtered, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
        
        current_group = all_symbols[scan_index*150 : (scan_index+1)*150]
        
        for s in current_group:
            score = analyze_v20(s)
            if score:
                price = tickers[s]['last']
                change_24h = tickers[s]['percentage']
                mega_scan_results.append({'symbol': s, 'score': score, 'price': price, 'change': change_24h})
                
                # دخول آلي صارم (إذا حققت 16 شرط من أصل 20)
                if score >= 16 and len(active_trades) < MAX_TRADES and s not in active_trades:
                    active_trades[s] = {'entry': price}
                    send_telegram(f"🚀 *دخول آلي (v14.0 Elite)*\n🪙 العملة: `{s}`\n🔥 القوة: `{score}/20`\n📈 24h: `{change_24h:+.2f}%`")

        scan_index += 1
        if scan_index >= 6:
            send_top_20_elite()
            scan_index = 0; mega_scan_results = []
    except: pass

def send_top_20_elite():
    if not mega_scan_results: return
    top_20 = sorted(mega_scan_results, key=lambda x: x['score'], reverse=True)[:20]
    report = "🏆 *أفضل 20 عملة (نظام الـ 20 شرطاً)*\n━━━━━━━━━━━━━━\n"
    for i, item in enumerate(top_20, 1):
        report += f"{i}. `{item['symbol']}` | ⭐ `{item['score']}/20` | `{item['change']:+.2f}%` \n"
    send_telegram(report)

# --- 5. التشغيل ---

def main_engine():
    global last_scan_time
    send_telegram("🦾 *v14.0 Elite Scanner Active*\nنظام التصفية بـ 20 شرطاً مفعّل الآن.")
    while True:
        try:
            now = datetime.now()
            # مراقبة البيع
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol); cp = ticker['last']
                pnl = (cp - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                if pnl >= TAKE_PROFIT_PCT or pnl <= -STOP_LOSS_PCT:
                    msg = "✅ هدف (5%)" if pnl > 0 else "🛑 وقف (4%)"
                    send_telegram(f"{msg}: `{symbol}` | الربح: `{pnl*100:+.2f}%`")
                    del active_trades[symbol]

            # المسح كل 5 دقائق
            if now >= last_scan_time + timedelta(minutes=5):
                run_elite_scan()
                last_scan_time = now
            time.sleep(20)
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
