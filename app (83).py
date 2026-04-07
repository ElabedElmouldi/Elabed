import ccxt
import pandas as pd
import numpy as np
import time
import requests
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات العامة (التجريبية) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
SERVER_URL = "https://your-app-name.onrender.com" # ضع رابط سيرفر Render هنا

# الربط العام بجلب البيانات (بدون مفاتيح حقيقية للتجربة)
exchange = ccxt.binance({'enableRateLimit': True})

# الثوابت
MAX_TRADES = 5
COST_PER_TRADE = 100
STABLE_COINS = ['USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP']
BIG_CAPS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']

active_trades = {}
closed_today = []
hourly_cache = {}
last_hourly_update = 0

app = Flask(__name__)

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك مراقبة الصفقات والتتبع السعري (10 ثوانٍ) ---

def monitor_loop():
    global closed_today
    while True:
        try:
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                
                # جلب السعر اللحظي
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100

                # أ. تفعيل نظام التتبع عند وصول الربح لـ 4%
                if res_pct >= 4.0:
                    if not trade['trailing_active']:
                        trade['trailing_active'] = True
                        send_telegram(f"🎯 *بدء التتبع السعري*: `{sym}`\nالربح الحالي: `{res_pct:.2f}%`\nالمراقبة الآن فائقة السرعة (10ث) بفارق 2%")
                    
                    # تحديث الوقف المتحرك (Trailing Stop)
                    # الوقف الجديد = أعلى سعر وصل له - 2%
                    new_sl = cp * 0.98 
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                    
                    # زيادة سرعة التحديث بناءً على طلبك (10 ثوانٍ)
                    time.sleep(10)

                # ب. شروط الإغلاق (الهدف 4% أو ضرب الوقف 2% أو التتبع)
                if cp >= trade['tp'] or cp <= trade['sl']:
                    duration = str(datetime.now() - trade['start_time']).split('.')[0]
                    final_res = ((cp - trade['entry']) / trade['entry']) * 100
                    
                    status = "✅ هدف كامل" if cp >= trade['tp'] else "📉 خروج (وقف/تتبع)"
                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{sym}`\n📊 النتيجة: `{final_res:+.2f}%` ({status})\n⏱️ المدة: `{duration}`")
                    
                    closed_today.append({'sym': sym, 'res': final_res, 'time': datetime.now().strftime('%H:%M')})
                    del active_trades[sym]
            
            time.sleep(20) # السرعة العادية للمراقبة
        except Exception as e:
            print(f"Monitor Error: {e}")
            time.sleep(10)

# --- 3. رادار التحليل وفلتر الـ 4% و 2% ---

def update_global_cache():
    global hourly_cache, last_hourly_update
    print("🔄 جاري تحديث قائمة الـ 10 عملات الأفضل...")
    try:
        tickers = exchange.fetch_tickers()
        all_symbols = [s for s in tickers if s.endswith('/USDT') and s not in BIG_CAPS 
                       and s.split('/')[0] not in STABLE_COINS][:300]
        
        temp_list = []
        for sym in all_symbols:
            try:
                # فلتر الاتجاه على فريم الساعة
                o1 = exchange.fetch_ohlcv(sym, '1h', limit=24)
                df = pd.DataFrame(o1, columns=['t','o','h','l','c','v'])
                mom = ((df['c'].iloc[-1] - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
                
                # إلزامي: السعر فوق EMA 10
                if df['c'].iloc[-1] > df['c'].ewm(span=10).mean().iloc[-1]:
                    temp_list.append({'symbol': sym, 'mom': mom, 'high_1h': df['h'].max()})
            except: continue
            
        # اختيار أفضل 10 عملات من حيث الزخم
        top_10 = sorted(temp_list, key=lambda x: x['mom'], reverse=True)[:10]
        hourly_cache = {x['symbol']: x for x in top_10}
        last_hourly_update = time.time()
    except: pass

def analyze_symbol(symbol):
    try:
        h_info = hourly_cache.get(symbol)
        o15 = exchange.fetch_ohlcv(symbol, '15m', limit=20)
        df15 = pd.DataFrame(o15, columns=['t','o','h','l','c','v'])
        cp = df15['c'].iloc[-1]
        
        # شرط الاختراق: السعر تجاوز أعلى قمة في الساعة الماضية
        if cp >= h_info['high_1h']:
            tp_price = cp * 1.04 # الهدف 4%
            sl_price = cp * 0.98 # الوقف 2% (إلزامي)
            
            # التأكد من عدم وجود تداخل أو خطأ في الحساب
            if (tp_price - cp) / cp >= 0.04:
                return {'symbol': symbol, 'price': cp, 'tp': tp_price, 'sl': sl_price}
    except: return None

def radar_loop():
    send_telegram("🦾 *AI Sniper V10 PRO*\nالنظام: وضع تجريبي كامل\nالشروط: ربح 4% / خسارة 2%\nالتتبع: مفعل عند 4% بفارق 2%")
    while True:
        try:
            if time.time() - last_hourly_update > 3600: update_global_cache()
            
            targets = list(hourly_cache.keys())
            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(analyze_symbol, targets)))
            
            for res in results:
                if res['symbol'] not in active_trades and len(active_trades) < MAX_TRADES:
                    active_trades[res['symbol']] = {
                        'entry': res['price'], 'tp': res['tp'], 'sl': res['sl'], 
                        'start_time': datetime.now(), 'trailing_active': False
                    }
                    send_telegram(f"🚀 *فتح صفقة تجريبية*\n🪙 `{res['symbol']}`\n💰 الدخول: `{res['price']}`\n🎯 الهدف: `{res['tp']}` (+4%)\n🛡️ الوقف: `{res['sl']}` (-2%)")
            
            time.sleep(600) # فحص كل 10 دقائق للرادار
        except: time.sleep(60)

# --- 4. التقارير والنشاط ---

def hourly_report():
    while True:
        time.sleep(3600)
        msg = f"📊 *تقرير الساعة*\nالصفقات المفتوحة: `{len(active_trades)}`"
        if closed_today:
            msg += f"\nمغلق اليوم: `{len(closed_today)}`"
        send_telegram(msg)

@app.route('/')
def health(): return "Bot Running", 200

if __name__ == "__main__":
    update_global_cache()
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    Thread(target=hourly_report, daemon=True).start()
    # نظام الـ Ping للبقاء نشطاً
    Thread(target=lambda: [(requests.get(SERVER_URL), time.sleep(300)) for _ in iter(int, 1)], daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
