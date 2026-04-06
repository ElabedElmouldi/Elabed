import ccxt
import pandas as pd
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

# --- 3. دالة الـ 20 شرطاً (نسخة سريعة - Optimized) ---
def analyze_fast_v20(symbol, ticker_data):
    try:
        # تقليل limit إلى 40 لتسريع الجلب (كافي للمؤشرات)
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=40)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        c = df['c']
        
        # حساب سريع للمؤشرات
        ema8 = c.ewm(span=8).mean(); ema20 = c.ewm(span=20).mean(); ema50 = c.ewm(span=50).mean()
        std = c.rolling(20).std()
        upper_bb = ema20 + (std * 2)
        
        delta = c.diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))

        score = 0
        # الفلاتر الإجبارية أولاً لتوفير الوقت
        price_change_24h = ticker_data['percentage']
        if (c.iloc[-1] - c.iloc[-4])/c.iloc[-4] > 0.07: return None # فلتر الانفجار الزائد
        
        # تطبيق الشروط الـ 20 (مختصرة برمجياً)
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2: score += 4
        if c.iloc[-1] > ema8.iloc[-1] > ema20.iloc[-1]: score += 3
        if 55 < rsi.iloc[-1] < 75: score += 3
        if c.iloc[-1] > upper_bb.iloc[-1]: score += 3
        if c.iloc[-1] > df['h'].iloc[-10:-1].max(): score += 3
        if c.iloc[-1] > df['o'].iloc[-1] * 1.01: score += 4

        return {'symbol': symbol, 'score': score, 'price': ticker_data['last'], 'change': price_change_24h} if score >= 12 else None
    except: return None

# --- 4. محرك المسح التوربيني (Turbo Scanner) ---
def run_turbo_scan():
    try:
        tickers = exchange.fetch_tickers()
        # تصفية الـ 900 عملة الأنشط
        all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
        all_symbols = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
        
        results = []
        send_telegram("🚀 *بدء مسح توربيني شامل لـ 900 عملة...*")
        
        # المسح في دورة واحدة سريعة
        for s in all_symbols:
            res = analyze_fast_v20(s, tickers[s])
            if res:
                results.append(res)
                # دخول آلي فوري للأقوى
                if res['score'] >= 18 and len(active_trades) < MAX_TRADES and s not in active_trades:
                    active_trades[s] = {'entry': res['price']}
                    send_telegram(f"⚡ *قنص سريع:* `{s}` | القوة: `{res['score']}/20`")
            
            # تأخير بسيط جداً لتجنب الحظر (Rate Limit)
            time.sleep(0.05) 

        # إرسال التقرير فور انتهاء المسح (كل 10 دقائق تقريباً)
        if results:
            top_20 = sorted(results, key=lambda x: x['score'], reverse=True)[:20]
            report = "🏆 *نخبة الـ 900 (تحديث توربيني)*\n━━━━━━━━━━━━━━\n"
            for i, item in enumerate(top_20, 1):
                report += f"{i}. `{item['symbol']}` | ⭐ `{item['score']}/20` | `{item['change']:+.2f}%` \n"
            send_telegram(report)
            
    except Exception as e:
        print(f"Turbo Scan Error: {e}")

# --- 5. المحرك الرئيسي ---
def main_engine():
    send_telegram("🏎️ *v15.0 Turbo Sniper Deployed*\nمسح شامل كل 10 دقائق.")
    while True:
        try:
            # 1. فحص الأرباح
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                pnl = (ticker['last'] - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                if pnl >= TAKE_PROFIT_PCT or pnl <= -STOP_LOSS_PCT:
                    msg = "🎯 ربح (5%)" if pnl > 0 else "🛑 وقف (4%)"
                    send_telegram(f"{msg}: `{symbol}` ({pnl*100:+.2f}%)")
                    del active_trades[symbol]

            # 2. تشغيل المسح التوربيني
            run_turbo_scan()
            
            # الراحة بين المسح والآخر (مثلاً 5 دقائق هدوء)
            time.sleep(300) 
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
