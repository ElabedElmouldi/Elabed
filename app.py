import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام (يرجى التأكد من التوكن والمعرفات) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية والتقنية ---
MAX_TRADES = 10         # أقصى عدد صفقات مفتوحة في وقت واحد
TRADE_AMOUNT = 100      # مبلغ الصفقة الواحدة (افتراضي)
ACTIVATION_PROFIT = 0.05 # يبدأ تتبع الربح بعد صعود 5%
TRAILING_GAP = 0.02      # مساحة التتبع (2%) للسماح للسعر بالتنفس
STOP_LOSS_PCT = 0.04     # وقف خسارة ثابت عند 4%

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

active_trades = {}  # مخزن الصفقات الحالية
mega_results = []   # مخزن نتائج المسح للتقرير

# --- 3. خوارزمية التصفية (20 شرطاً مطوراً) ---
def analyze_v20_elite(symbol, ticker):
    try:
        # جلب بيانات الشموع (15 دقيقة)
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        c = df['c']
        
        # حساب المؤشرات الأساسية
        ema8 = c.ewm(span=8).mean(); ema20 = c.ewm(span=20).mean(); ema50 = c.ewm(span=50).mean()
        std = c.rolling(20).std(); upper_bb = ema20 + (std * 2)
        
        # RSI
        delta = c.diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))

        score = 0
        # [الفئة 1: السيولة - 6 نقاط]
        if df['v'].iloc[-1] > df['v'].iloc[-20:-1].mean() * 2.5: score += 3
        if (c.iloc[-1] * df['v'].iloc[-1]) > 50000: score += 3
        
        # [الفئة 2: الزخم والاتجاه - 6 نقاط]
        if c.iloc[-1] > ema8.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]: score += 3
        if 55 < rsi.iloc[-1] < 75: score += 3
        
        # [الفئة 3: الانفجار الفني - 4 نقاط]
        if c.iloc[-1] > upper_bb.iloc[-1]: score += 2
        if c.iloc[-1] > df['h'].iloc[-15:-1].max(): score += 2
        
        # [الفئة 4: سلوك الشمعة - 4 نقاط]
        body = abs(c.iloc[-1] - df['o'].iloc[-1])
        wick = df['h'].iloc[-1] - max(c.iloc[-1], df['o'].iloc[-1])
        if c.iloc[-1] > df['o'].iloc[-1] and wick < (body * 0.2): score += 4

        # فلاتر الحماية الإلزامية
        if (c.iloc[-1] - ema20.iloc[-1])/ema20.iloc[-1] > 0.06: return None # تجنب الانفجار المفرط
        
        return {'symbol': symbol, 'score': score, 'price': ticker['last'], 'chg': ticker['percentage']} if score >= 12 else None
    except: return None

# --- 4. محرك تتبع السعر (كل 10 ثوانٍ) ---
def trade_monitor_thread():
    while True:
        try:
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                current_p = ticker['last']
                trade = active_trades[symbol]
                
                # تحديث أعلى سعر وصل له السعر منذ الدخول
                if current_p > trade['highest_price']:
                    active_trades[symbol]['highest_price'] = current_p
                
                gain = (current_p - trade['entry']) / trade['entry']
                
                # أ. وقف الخسارة الثابت (4%)
                if gain <= -STOP_LOSS_PCT:
                    send_telegram(f"🛑 *إغلاق (وقف خسارة):* `{symbol}`\n📉 النسبة: `{gain*100:.2f}%`")
                    del active_trades[symbol]
                    continue

                # ب. جني الأرباح المتحرك (بعد صعود 5% مع تراجع 2%)
                highest = active_trades[symbol]['highest_price']
                drop_from_top = (highest - current_p) / highest
                
                if gain >= ACTIVATION_PROFIT:
                    if drop_from_top >= TRAILING_GAP:
                        final_pnl = (current_p - trade['entry']) / trade['entry'] * 100
                        send_telegram(
                            f"💰 *جني أرباح (تتبع 2%):* `{symbol}`\n"
                            f"✅ الربح المحقق: `{final_pnl:.2f}%` \n"
                            f"🔝 أعلى قمة: `{highest}`"
                        )
                        del active_trades[symbol]
            
            time.sleep(10) # فحص دقيق كل 10 ثوانٍ
        except: time.sleep(5)

# --- 5. محرك المسح التوربيني لـ 900 عملة ---
def run_turbo_scanner():
    global mega_results
    while True:
        try:
            tickers = exchange.fetch_tickers()
            all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
            # ترتيب حسب السيولة واختيار أعلى 900
            target_symbols = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
            
            current_scan_results = []
            send_telegram("🛰️ *بدء دورة مسح شاملة لـ 900 عملة...*")

            for s in target_symbols:
                res = analyze_v20_elite(s, tickers[s])
                if res:
                    current_scan_results.append(res)
                    # فتح صفقة تلقائية إذا كانت الإشارة قوية جداً
                    if res['score'] >= 17 and len(active_trades) < MAX_TRADES and s not in active_trades:
                        entry_p = res['price']
                        active_trades[s] = {
                            'entry': entry_p,
                            'highest_price': entry_p,
                            'time': datetime.now().strftime('%H:%M:%S')
                        }
                        # إرسال إشعار الدخول التفصيلي
                        send_telegram(
                            f"🔔 *دخول صفقة شراء*\n━━━━━━━━━━━━━━\n"
                            f"🪙 العملة: `{s}`\n💰 سعر الدخول: `{entry_p}`\n"
                            f"🛑 الوقف: `{entry_p * (1-STOP_LOSS_PCT):.8f}`\n"
                            f"🎯 هدف التتبع: `>5%`\n⭐ القوة: `{res['score']}/20`\n"
                            f"⏰ الوقت: `{datetime.now().strftime('%H:%M:%S')}`"
                        )
                time.sleep(0.04) # حماية من الـ Rate Limit

            # إرسال تقرير أفضل 20 عملة بعد كل مسح
            if current_scan_results:
                top_20 = sorted(current_scan_results, key=lambda x: x['score'], reverse=True)[:20]
                report = "🏆 *قائمة النخبة (أفضل 20 فرصة)*\n━━━━━━━━━━━━━━\n"
                for i, item in enumerate(top_20, 1):
                    report += f"{i}. `{item['symbol']}` | ⭐ `{item['score']}/20` | `{item['chg']:+.2f}%` \n"
                send_telegram(report)

            time.sleep(300) # راحة 5 دقائق بين كل مسح شامل
        except: time.sleep(60)

# --- 6. التشغيل النهائي ---
if __name__ == "__main__":
    # واجهة بسيطة للسيرفر (Render/PythonAnywhere)
    app = Flask('')
    @app.route('/')
    def home(): return "<h1>Sniper v16.2 Active</h1>"
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    
    # تشغيل خيط مراقبة الصفقات (10 ثوانٍ)
    Thread(target=trade_monitor_thread).start()
    
    # تشغيل محرك المسح الرئيسي
    run_turbo_scanner()
