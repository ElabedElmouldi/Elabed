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

# --- 2. الإعدادات المالية والفنية (Trailing Logic) ---
MAX_TRADES = 20
TRADE_AMOUNT = 25
STOP_LOSS_PCT = 0.03          # وقف خسارة ثابت 3% لحماية رأس المال
ACTIVATION_PCT = 0.03         # تفعيل التتبع عند وصول الربح لـ 3%
TRAILING_CALLBACK = 0.008     # ملاحقة السعر بفرق 0.8% (Callback)

VOL_MIN = 15000000
VOL_MAX = 500000000

exchange = ccxt.binance({'enableRateLimit': True})

# إدارة البيانات
active_trades = {}            # { 'SYM': {entry, sl, highest_p, trailing_active, start_time} }
daily_closed_trades = []
last_report_1h = datetime.now()
last_radar_scan = datetime.now()

# --- 3. خوارزمية البحث (السيولة + الضغط + RSI) ---
def analyze_signal_pro(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['ma20'] = df['c'].rolling(20).mean()
        df['std'] = df['c'].rolling(20).std()
        width = (df['std'] * 4) / df['ma20']
        
        recent_vol_avg = df['v'].iloc[-6:-1].mean()
        current_vol = df['v'].iloc[-1]
        
        # RSI Calculation
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]

        # شروط الانفجار
        is_squeezed = width.iloc[-1] < width.rolling(50).mean().iloc[-1] * 0.95
        is_vol_breakout = current_vol > (recent_vol_avg * 2)
        is_momentum_good = 50 < rsi < 68

        if is_squeezed and is_vol_breakout and is_momentum_good:
            return {'price': df['c'].iloc[-1], 'rsi': rsi, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك الرئيسي (Trailing Execution) ---
def main_engine():
    global last_report_1h, last_radar_scan
    send_telegram("🦾 *تم تشغيل القناص v8.3 (Trailing Stop)*\n- تفعيل التتبع: `عند +3%`\n- الملاحقة: `بفرق 0.8%`\n- الحد الأقصى: `20 صفقة`")

    while True:
        try:
            now = datetime.now()

            # أ. إدارة ومراقبة الصفقات (منطق التتبع)
            for symbol in list(active_trades.keys()):
                try:
                    curr_p = exchange.fetch_ticker(symbol)['last']
                    trade = active_trades[symbol]
                    
                    # تحديث أعلى سعر وصل له السعر منذ الدخول
                    if curr_p > trade['highest_p']:
                        trade['highest_p'] = curr_p
                    
                    # 1. تفعيل وضع التتبع (بمجرد لمس 3% ربح)
                    if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                        trade['trailing_active'] = True
                        send_telegram(f"🎯 *تفعيل التتبع:* `{symbol}` وصل للهدف الأول (3%+). البوت الآن يلاحق القمة!")

                    # 2. قرار الإغلاق
                    close_reason = ""
                    # حالة أ: ضرب وقف الخسارة الثابت (قبل تفعيل التتبع)
                    if not trade['trailing_active'] and curr_p <= trade['sl']:
                        close_reason = "🛑 وقف خسارة"
                    
                    # حالة ب: السعر تراجع عن القمة بـ 0.8% (بعد تفعيل التتبع)
                    elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK):
                        close_reason = "💰 جني أرباح (تتبع)"

                    if close_reason:
                        pnl = (curr_p - trade['entry']) / trade['entry']
                        duration = str(now - trade['start']).split('.')[0]
                        
                        msg = (f"{close_reason}: `{symbol}`\n"
                               f"📊 النتيجة: `{pnl*100:+.2f}%`\n"
                               f"⏱️ المدة: `{duration}`\n"
                               f"📈 سعر الخروج: `{curr_p:.4f}`")
                        send_telegram(msg)
                        
                        daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'duration': duration})
                        del active_trades[symbol]
                except: continue

            # ب. البحث والدخول (20 صفقة)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                symbols_to_scan = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:300]
                
                for s in symbols_to_scan:
                    if len(active_trades) >= MAX_TRADES or s in active_trades: continue
                    
                    sig = analyze_signal_pro(s)
                    if sig and sig['ready']:
                        entry_p = sig['price']
                        active_trades[s] = {
                            'entry': entry_p,
                            'sl': entry_p * (1 - STOP_LOSS_PCT),
                            'highest_p': entry_p,
                            'trailing_active': False,
                            'start': now
                        }
                        
                        send_telegram(f"🚀 *دخول صفقة:* `{s}`\n💰 السعر: `{entry_p:.4f}`\n⏰ الوقت: `{now.strftime('%H:%M:%S')}`\n🛑 الوقف الأولي: `{active_trades[s]['sl']:.4f}`")

            # ج. الرادار (15 دقيقة) والتقرير (ساعة)
            if now >= last_radar_scan + timedelta(minutes=15):
                # (كود إرسال قائمة الـ 20 عملة كما في v8.2)
                last_radar_scan = now

            if now >= last_report_1h + timedelta(hours=1):
                # (كود إرسال التقرير الشامل كما في v8.2)
                last_report_1h = now

            time.sleep(45) # فحص سريع للملاحقة
        except: time.sleep(30)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Sniper Trailing v8.3 Active"
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    main_engine()
