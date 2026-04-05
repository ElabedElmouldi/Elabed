import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام (بياناتك الخاصة) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية والفنية ---
MAX_TRADES = 20               # الحد الأقصى للصفقات المفتوحة
TRADE_AMOUNT = 25             # مبلغ الدخول لكل صفقة (دولار)
TAKE_PROFIT_PCT = 0.03        # هدف الربح 3%
STOP_LOSS_PCT = 0.03          # وقف الخسارة 3%
VOL_MIN = 15000000            # الحد الأدنى للسيولة (15 مليون $)
VOL_MAX = 500000000           # الحد الأقصى (استبعاد العملات الكبيرة)

exchange = ccxt.binance({'enableRateLimit': True})

# إدارة البيانات الحية
active_trades = {}            # { 'SYMBOL': {entry, tp, sl, start_time} }
daily_closed_trades = []      # سجل الصفقات المغلقة اليوم
last_report_1h = datetime.now()
last_radar_scan = datetime.now()

# --- 3. خوارزمية البحث المتطورة (Advanced Explosion Search) ---
def analyze_signal_pro(symbol):
    try:
        # جلب 100 شمعة لتحليل أدق للاتجاه والضغط
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # أ. حساب ضغط البولنجر (Squeeze)
        df['ma20'] = df['c'].rolling(20).mean()
        df['std'] = df['c'].rolling(20).std()
        # عرض النطاق (Width)
        df['width'] = (df['std'] * 4) / df['ma20']
        
        # ب. حساب قوة السيولة (Volume Force)
        # مقارنة الفوليوم الحالي بمتوسط الـ 5 شمعات السابقة مباشرة
        recent_vol_avg = df['v'].iloc[-6:-1].mean()
        current_vol = df['v'].iloc[-1]
        
        # ج. حساب مؤشر RSI (الزخم)
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        # --- شروط الاقتناص الاحترافية ---
        # 1. السعر في حالة ضغط (أقل من متوسط ضغط آخر 50 شمعة)
        is_squeezed = df['width'].iloc[-1] < df['width'].rolling(50).mean().iloc[-1] * 0.95
        # 2. انفجار سيولة مفاجئ (أكبر من ضعف المتوسط القريب)
        is_vol_breakout = current_vol > (recent_vol_avg * 2)
        # 3. زخم صاعد صحي (بين 50 و 68) لضمان بداية الحركة
        is_momentum_good = 50 < rsi < 68

        if is_squeezed and is_vol_breakout and is_momentum_good:
            return {'price': df['c'].iloc[-1], 'rsi': rsi, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك الرئيسي لإدارة المحفظة ---
def main_engine():
    global last_report_1h, last_radar_scan
    send_telegram("🦾 *تم تشغيل القناص المطور v8.2*\n- النظام: `20 صفقة × 25$`\n- فلاتر: `Squeeze + Vol x2 + RSI`\n- الرادار: `تحديث كل 15 دقيقة`")

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة وإغلاق الصفقات (الهدف أو الوقف)
            for symbol in list(active_trades.keys()):
                try:
                    curr_p = exchange.fetch_ticker(symbol)['last']
                    data = active_trades[symbol]
                    
                    # التحقق من جني الأرباح (3%) أو وقف الخسارة (3%)
                    if curr_p >= data['tp'] or curr_p <= data['sl']:
                        pnl = (curr_p - data['entry']) / data['entry']
                        duration = str(now - data['start']).split('.')[0] # حساب المدة
                        icon = "✅ ربح" if pnl > 0 else "🛑 خسارة"
                        
                        msg = (f"{icon} *إغلاق صفقة:* `{symbol}`\n"
                               f"📊 النتيجة: `{pnl*100:+.2f}%`\n"
                               f"⏱️ مدة الصفقة: `{duration}`\n"
                               f"📈 سعر الخروج: `{curr_p:.4f}`")
                        send_telegram(msg)
                        
                        daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'duration': duration})
                        del active_trades[symbol]
                except: continue

            # ب. الدخول التلقائي في صفقات جديدة (حتى 20 صفقة)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                symbols_to_scan = [s for s, d in all_tickers.items() 
                                   if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:300]
                
                for s in symbols_to_scan:
                    if len(active_trades) >= MAX_TRADES: break
                    if s in active_trades: continue
                    
                    sig = analyze_signal_pro(s)
                    if sig and sig['ready']:
                        entry_p = sig['price']
                        tp_val = entry_p * (1 + TAKE_PROFIT_PCT)
                        sl_val = entry_p * (1 - STOP_LOSS_PCT)
                        
                        active_trades[s] = {
                            'entry': entry_p, 'tp': tp_val, 'sl': sl_val, 'start': now
                        }
                        
                        # إشعار الدخول التفصيلي
                        entry_msg = (f"🚀 *فتح صفقة جديدة*\n\n"
                                     f"💎 العملة: `{s}`\n"
                                     f"💰 سعر الدخول: `{entry_p:.4f}`\n"
                                     f"⏰ وقت الدخول: `{now.strftime('%H:%M:%S')}`\n"
                                     f"🎯 الهدف (3%): `{tp_val:.4f}`\n"
                                     f"🛑 الوقف (3%): `{sl_val:.4f}`\n"
                                     f"📈 مؤشر RSI: `{sig['rsi']:.1f}`")
                        send_telegram(entry_msg)
                        time.sleep(1)

            # ج. رادار الـ 15 دقيقة (قائمة أفضل 20 عملة مرشحة)
            if now >= last_radar_scan + timedelta(minutes=15):
                all_tickers = exchange.fetch_tickers()
                potential = [s for s, d in all_tickers.items() if '/USDT' in s and VOL_MIN < d['quoteVolume'] < VOL_MAX][:300]
                
                radar_results = []
                for s in potential:
                    res = analyze_signal_pro(s)
                    if res and res['ready']:
                        radar_results.append(f"- `{s}` (RSI: {res['rsi']:.1f})")
                
                if radar_results:
                    send_telegram(f"🔍 *رادار الـ 15 دقيقة (أفضل الفرص):*\n" + "\n".join(radar_results[:20]))
                last_radar_scan = now

            # د. تقرير الساعة الشامل (المفتوحة والمغلقة)
            if now >= last_report_1h + timedelta(hours=1):
                report = f"📊 *تقرير الساعة ({now.strftime('%H:%M')})*\n\n"
                report += "*📂 صفقات مفتوحة حالياً:*\n"
                for s, d in active_trades.items():
                    curr_p = exchange.fetch_ticker(s)['last']
                    cur_pnl = (curr_p - d['entry']) / d['entry'] * 100
                    report += f"- `{s}`: `{cur_pnl:+.2f}%`\n"
                if not active_trades: report += "لا يوجد\n"
                
                report += "\n*📜 سجل الإغلاق اليومي:*\n"
                for t in daily_closed_trades:
                    report += f"- `{t['symbol']}` ({t['pnl']*100:+.2f}%) | `{t['duration']}`\n"
                if not daily_closed_trades: report += "لا يوجد"
                
                send_telegram(report)
                last_report_1h = now

            time.sleep(60) # تحديث الحالة كل دقيقة
        except Exception as e:
            time.sleep(30)

# --- 5. تشغيل السيرفر والمنطق ---
if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Sniper v8.2 Live | Trades: {len(active_trades)}"
    
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    main_engine()
