import ccxt
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "bot_data.json"
APP_URL = "your-app-name.onrender.com" # ⚠️ استبدله برابطك في Render

exchange = ccxt.binance({
    'apiKey': os.environ.get('BINANCE_API_KEY', ''),
    'secret': os.environ.get('BINANCE_SECRET', ''),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

MAX_TRADES = 10
TRADE_AMOUNT_USD = 100.0
SCAN_INTERVAL = 900 # 15 دقيقة
STOP_LOSS_PCT = 0.02       
ACTIVATION_PROFIT = 0.04   
TRAILING_GAP = 0.02        
STABLE_COINS = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'USDT']

# --- 2. إدارة البيانات ---
active_trades = {}
wallet_balance = 1000.0
daily_start_balance = 1000.0
last_reset_date = str(datetime.now().date())

def save_data():
    try:
        data = {'wallet_balance': wallet_balance, 'active_trades': active_trades, 
                'daily_start_balance': daily_start_balance, 'last_reset_date': last_reset_date}
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
    except: pass

def load_data():
    global wallet_balance, active_trades, daily_start_balance, last_reset_date
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                wallet_balance = data.get('wallet_balance', 1000.0)
                active_trades = data.get('active_trades', {})
                daily_start_balance = data.get('daily_start_balance', wallet_balance)
                last_reset_date = data.get('last_reset_date', str(datetime.now().date()))
        except: pass

load_data()

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                           json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. فحص حالة البيتكوين ---
def get_btc_status():
    try:
        btc_bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=2)
        change = (btc_bars[-1][4] - btc_bars[-2][4]) / btc_bars[-2][4]
        # إذا هبط البيتكوين بأكثر من 1% نعتبر السوق غير آمن
        return "UNSAFE" if change < -0.01 else "SAFE"
    except: return "SAFE"

# --- 4. محرك التحليل (Scoring) ---
def get_breakout_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        avg_v = df['v'].tail(20).mean()
        score = 0
        if cp > ema20: score += 2
        if df['v'].iloc[-1] > avg_v * 2: score += 5
        if cp > df['h'].iloc[-2]: score += 3
        if cp > df['o'].iloc[-1]: score += 2
        if df['v'].iloc[-1] > df['v'].iloc[-2]: score += 3
        if ((cp - df['o'].iloc[-1])/df['o'].iloc[-1]) > 0.006: score += 5
        return score, cp
    except: return 0, 0

# --- 5. أنظمة المراقبة ومنع النوم ---
def monitor_thread():
    global wallet_balance
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']
                trade = active_trades[s]
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                    if not trade.get('tr_act', False) and ((cp - trade['entry']) / trade['entry']) >= ACTIVATION_PROFIT:
                        active_trades[s]['tr_act'] = True
                        send_telegram(f"🚀 *تنشيط التتبع:* `{s}` (+4%)")
                        save_data()
                
                highest = active_trades[s]['highest_price']
                gain = (cp - trade['entry']) / trade['entry']
                drop = (highest - cp) / highest
                exit_now = False
                if trade.get('tr_act', False) and drop >= TRAILING_GAP: exit_now = True
                elif not trade.get('tr_act', False) and gain <= -STOP_LOSS_PCT: exit_now = True

                if exit_now:
                    pnl_usd = TRADE_AMOUNT_USD * gain
                    wallet_balance += pnl_usd
                    send_telegram(f"🏁 *إغلاق صفقة:* `{s}`\n📈 النتيجة: `{gain*100:+.2f}%`\n💰 المحفظة: `{wallet_balance:.2f}$` ")
                    del active_trades[s]; save_data()
            time.sleep(10)
        except: time.sleep(5)

def self_ping_thread():
    while True:
        try:
            url = f"https://{APP_URL}" if not APP_URL.startswith("http") else APP_URL
            requests.get(url, timeout=15)
        except: pass
        time.sleep(300)

# --- 6. المحرك الرئيسي: القناص المرن ---
def main_engine():
    send_telegram("🛡️ *Sniper v290.0 Online*\nوضع القناص المرن: إشعارات مستمرة حتى في هبوط السوق.")
    
    # يبدأ المسح الأول فوراً
    last_scan = datetime.now() - timedelta(seconds=SCAN_INTERVAL)
    
    while True:
        try:
            now = datetime.now()
            if now >= last_scan + timedelta(seconds=SCAN_INTERVAL):
                btc_status = get_btc_status()
                
                # إذا كان السوق هابطاً، نرسل تنبيه "غير آمن" ونواصل العمل
                if btc_status == "UNSAFE":
                    send_telegram("⚠️ *تنبيه:* السوق حالياً غير آمن (BTC هابط)، سأواصل البحث عن العملات المتمردة فقط (سكور 16+).")

                print(f"🔄 جاري المسح... حالة السوق: {btc_status}")
                markets = exchange.fetch_markets()
                all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot'] and m['base'] not in STABLE_COINS]
                tickers = exchange.fetch_tickers(all_usdt)
                targets = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[10:310]

                with ThreadPoolExecutor(max_workers=10) as executor:
                    raw_res = list(executor.map(lambda s: {'s': s, 'd': get_breakout_score(s)}, targets))
                    res_sorted = sorted([r for r in raw_res if r['d'][0] > 0], key=lambda x: x['d'][0], reverse=True)

                if res_sorted:
                    # تقرير المسح الدوري
                    scan_rep = "🔍 *نتائج مسح السوق:*\n"
                    for i, r in enumerate(res_sorted[:5]):
                        scan_rep += f"{i+1}. `{r['s']}` ➟ `{r['d'][0]}/20` \n"
                    send_telegram(scan_rep)

                    # منطق الدخول الذكي:
                    best = res_sorted[0]
                    required_score = 16 if btc_status == "UNSAFE" else 12
                    
                    if best['d'][0] >= required_score:
                        if best['s'] not in active_trades and len(active_trades) < MAX_TRADES:
                            active_trades[best['s']] = {'entry': best['d'][1], 'highest_price': best['d'][1],
                                                       'entry_time': now.strftime('%Y-%m-%d %H:%M:%S'), 'tr_act': False}
                            save_data()
                            sl = best['d'][1] * (1 - STOP_LOSS_PCT)
                            msg = "🔥 *اقتناص عملة متمردة (عكس السوق):*" if btc_status == "UNSAFE" else "🎯 *اقتناص المركز الأول:*"
                            send_telegram(f"{msg}\n🪙 `{best['s']}`\n✅ السكور: `{best['d'][0]}`\n🛑 الوقف: `{sl:.6f}`")
                
                last_scan = now
            time.sleep(30)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(10)

# --- 7. التشغيل ---
app = Flask('')
@app.route('/')
def home(): return "Mouldi Sniper Active"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    Thread(target=self_ping_thread).start()
    main_engine()
