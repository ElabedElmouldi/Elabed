import ccxt
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "virtual_v350.json"
APP_URL = "your-app-name.onrender.com" 

exchange = ccxt.binance({'enableRateLimit': True})

SCAN_INTERVAL = 900 
MAX_VIRTUAL_TRADES = 5 
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
virtual_trades = {}
virtual_balance = 1000.0

def load_v_data():
    global virtual_balance, virtual_trades
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                virtual_balance = data.get('virtual_balance', 1000.0)
                virtual_trades = data.get('virtual_trades', {})
        except: pass

def save_v_data():
    try:
        data = {'virtual_balance': virtual_balance, 'virtual_trades': virtual_trades}
        with open(DATA_FILE, 'w') as f: json.dump(data, f)
    except: pass

load_v_data()

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. نظام التكيف مع السوق (Dynamic Logic) ---
def get_market_strategy():
    """تحديد حالة السوق وتغيير قوانين اللعبة آلياً"""
    try:
        btc_bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = (btc_bars[-1][4] - btc_bars[-2][4]) / btc_bars[-2][4]
        
        if change < -0.01: # سوق هابط (غير آمن)
            return {
                'status': "🚨 UNSAFE",
                'sl': 0.012,      # وقف خسارة ضيق جداً (1.2%)
                'act': 0.02,      # تنشيط التتبع مبكراً (2%)
                'gap': 0.008,     # ملاحقة قريبة جداً (0.8%)
                'min_score': 16   # لا يدخل إلا في "الأسود" فقط
            }
        else: # سوق مستقر (آمن)
            return {
                'status': "✅ SAFE",
                'sl': 0.02,       # وقف خسارة عادي (2%)
                'act': 0.04,      # تنشيط التتبع عند (4%)
                'gap': 0.02,      # ملاحقة عادية (2%)
                'min_score': 12   # دخول مرن
            }
    except:
        return {'status': "✅ SAFE", 'sl': 0.02, 'act': 0.04, 'gap': 0.02, 'min_score': 12}

# --- 4. محرك التحليل والمراقبة ---
def get_signal_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        rvol = df['v'].iloc[-1] / df['v'].tail(20).mean()
        
        score = 0
        if cp > df['c'].ewm(span=20).mean().iloc[-1]: score += 4
        if cp > df['h'].iloc[-2]: score += 4
        if rvol > 1.8: score += 12 
        return score, cp
    except: return 0, 0

def virtual_monitor():
    global virtual_balance
    while True:
        try:
            for s in list(virtual_trades.keys()):
                trade = virtual_trades[s]
                ticker = exchange.fetch_ticker(s); cp = ticker['last']
                
                if cp > trade.get('highest_price', 0):
                    virtual_trades[s]['highest_price'] = cp
                    # تنشيط التتبع بناءً على الاستراتيجية التي دخل بها
                    gain_now = (cp - trade['entry']) / trade['entry']
                    if not trade.get('tr_act', False) and gain_now >= trade['strategy']['act']:
                        virtual_trades[s]['tr_act'] = True
                        send_telegram(f"🛡️ *تأمين ربح افتراضي:* `{s}`\nتم تفعيل ملاحقة السعر.")

                highest = virtual_trades[s]['highest_price']
                gain = (cp - trade['entry']) / trade['entry']
                drop_from_top = (highest - cp) / highest
                
                # قوانين الخروج المرنة
                exit_now = False
                reason = ""
                if trade.get('tr_act', False) and drop_from_top >= trade['strategy']['gap']:
                    exit_now = True; reason = "💰 جني أرباح (ملاحقة)"
                elif not trade.get('tr_act', False) and gain <= -trade['strategy']['sl']:
                    exit_now = True; reason = "❌ وقف خسارة"

                if exit_now:
                    pnl = 100 * gain
                    virtual_balance += pnl
                    send_telegram(f"🏁 *إغلاق صفقة افتراضية:*\nالعملة: `{s}`\nالسبب: {reason}\nالنتيجة: `{gain*100:+.2f}%`\nالرصيد الوهمي: `{virtual_balance:.2f}$` ")
                    del virtual_trades[s]; save_v_data()
            time.sleep(20)
        except: time.sleep(10)

def radar_engine():
    send_telegram("🦎 *تم تشغيل القناص المتكيف (v350.0)*\nوضع المحاكاة: سأقوم بتغيير استراتيجيتي حسب حالة السوق.")
    last_scan = datetime.now() - timedelta(seconds=SCAN_INTERVAL)
    
    while True:
        try:
            now = datetime.now()
            if now >= last_scan + timedelta(seconds=SCAN_INTERVAL):
                # 1. فحص حالة السوق وتحديث الاستراتيجية
                strategy = get_market_strategy()
                send_telegram(f"🔍 *بدء المسح الدوري*\nحالة السوق: `{strategy['status']}`\nالهدف المفعّل: سكور `{strategy['min_score']}+`")

                # 2. جلب العملات والتحليل
                tickers = exchange.fetch_tickers()
                all_usdt = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]
                targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:150]

                with ThreadPoolExecutor(max_workers=10) as executor:
                    raw_res = list(executor.map(lambda s: {'s': s, 'd': get_signal_score(s)}, targets))
                    res_sorted = sorted([r for r in raw_res if r['d'][0] >= 10], key=lambda x: x['d'][0], reverse=True)

                if res_sorted:
                    report = "📋 *أفضل العملات المرصودة:*\n"
                    for r in res_sorted[:3]: report += f"• `{r['s']}` ➟ سكور: `{r['d'][0]}/20` \n"
                    send_telegram(report)

                    # 3. اتخاذ قرار الدخول الافتراضي
                    best = res_sorted[0]
                    if best['d'][0] >= strategy['min_score'] and best['s'] not in virtual_trades and len(virtual_trades) < MAX_VIRTUAL_TRADES:
                        virtual_trades[best['s']] = {
                            'entry': best['d'][1],
                            'highest_price': best['d'][1],
                            'tr_act': False,
                            'strategy': strategy # تخزين القوانين الخاصة بهذه الصفقة
                        }
                        save_v_data()
                        msg = "🔥 *اقتناص متمرد (عكس السوق):*" if strategy['status'] != "✅ SAFE" else "🎯 *دخول افتراضي جديد:*"
                        send_telegram(f"{msg}\nالعملة: `{best['s']}`\nالسعر: `{best['d'][1]}`\nالوقف: `{strategy['sl']*100}%` | التتبع: `{strategy['act']*100}%` ")
                
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

# --- 5. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Chameleon Simulator Active"

def self_ping():
    while True:
        try: requests.get(f"https://{APP_URL}", timeout=10)
        except: pass
        time.sleep(300)

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=virtual_monitor).start()
    Thread(target=self_ping).start()
    radar_engine()
