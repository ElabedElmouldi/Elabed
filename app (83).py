import ccxt
import pandas as pd
import numpy as np
import time
import requests
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات والبيانات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
SERVER_URL = "https://your-app-name.onrender.com"

exchange = ccxt.binance({'enableRateLimit': True})

# القوائم السوداء والمستبعدة
BIG_CAPS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
STABLE_COINS = ['USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP']

# إعدادات المحفظة الافتراضية
MAX_TRADES = 5
COST_PER_TRADE = 100
active_trades = {}
closed_today = []
blacklist_cooldown = {} # للعملات الخاسرة (ساعتين)
hourly_cache = {}
last_hourly_update = 0

app = Flask(__name__)

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

# --- 2. وظائف الحماية المتقدمة ---

def is_btc_safe():
    """فلتر سيد السوق: التأكد من أن البيتكوين مستقر أو صاعد"""
    try:
        btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '15m', limit=30)
        df = pd.DataFrame(btc_ohlcv, columns=['t','o','h','l','c','v'])
        ema20 = df['c'].ewm(span=20).mean().iloc[-1]
        return df['c'].iloc[-1] > ema20
    except: return False

def get_sector(symbol):
    """تصنيف تقريبي للقطاعات لتنويع المخاطر"""
    sectors = {
        'AI': ['FET', 'AGIX', 'OCEAN', 'RNDR', 'NEAR', 'TAO'],
        'MEME': ['PEPE', 'SHIB', 'DOGE', 'FLOKI', 'BONK', 'WIF', 'MEME'],
        'L1/L2': ['ARB', 'OP', 'MATIC', 'APT', 'SUI', 'SEI'],
        'GAMING': ['GALA', 'IMX', 'BEAM', 'AXS', 'SAND', 'MANA']
    }
    asset = symbol.split('/')[0]
    for sector, coins in sectors.items():
        if asset in coins: return sector
    return 'ALT' # قطاع عام

# --- 3. مراقبة الصفقات (الخروج الجزئي والتتبع) ---

def monitor_loop():
    global closed_today
    while True:
        try:
            btc_ok = is_btc_safe()
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                cp = exchange.fetch_ticker(sym)['last']
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100
                
                # أ. الخروج الجزئي (Partial TP) عند 2%
                if res_pct >= 2.0 and not trade['partial_exit']:
                    trade['partial_exit'] = True
                    trade['sl'] = trade['entry'] # رفع الوقف للدخول فوراً
                    send_telegram(f"💰 *خروج جزئي (50%)*: `{sym}`\nتم حجز ربح 2% ورفع الوقف لسعر الدخول 🛡️")

                # ب. التتبع السعري الفائق (كل 10 ثوانٍ عند الربح)
                if res_pct > 2.5:
                    trade['sl'] = max(trade['sl'], cp * 0.988) # تتبع بفرق 1.2%
                    time.sleep(10)

                # ج. شرط الإغلاق النهائي
                if cp >= trade['tp'] or cp <= trade['sl']:
                    duration = str(datetime.now() - trade['start_time']).split('.')[0]
                    final_res = res_pct
                    
                    status = "✅ ربح كامل" if cp >= trade['tp'] else ("🔒 خروج متعادل" if cp <= trade['sl'] and trade['partial_exit'] else "📉 وقف خسارة")
                    
                    # إضافة للـ Blacklist إذا كانت خسارة
                    if final_res < 0:
                        blacklist_cooldown[sym] = datetime.now() + timedelta(hours=2)

                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{sym}`\n📊 النتيجة: `{final_res:+.2f}%` \n⏱️ المدة: `{duration}`\n📝 الحالة: {status}")
                    closed_today.append({'sym': sym, 'res': final_res, 'time': datetime.now().strftime('%H:%M')})
                    del active_trades[sym]
            
            time.sleep(20)
        except: time.sleep(10)

# --- 4. الرادار والتحليل المتطور ---

def update_global_cache():
    global hourly_cache, last_hourly_update
    try:
        tickers = exchange.fetch_tickers()
        all_symbols = [s for s in tickers if s.endswith('/USDT') and s not in BIG_CAPS 
                       and s.split('/')[0] not in STABLE_COINS][:500]
        
        temp_data = []
        for sym in all_symbols:
            try:
                t = tickers[sym]
                if t['quoteVolume'] < 15000000: continue
                
                o4 = exchange.fetch_ohlcv(sym, '4h', limit=10)
                df4 = pd.DataFrame(o4, columns=['t','o','h','l','c','v'])
                if df4['c'].iloc[-1] < df4['c'].ewm(span=10).mean().iloc[-1]: continue
                
                o1 = exchange.fetch_ohlcv(sym, '1h', limit=24)
                df1 = pd.DataFrame(o1, columns=['t','o','h','l','c','v'])
                mom = ((df1['c'].iloc[-1] - df1['o'].iloc[0]) / df1['o'].iloc[0]) * 100
                
                temp_data.append({'symbol': sym, 'mom': mom, 'high_1h': df1['h'].max(), 'sector': get_sector(sym)})
            except: continue

        top_10 = sorted(temp_data, key=lambda x: x['mom'], reverse=True)[:10]
        hourly_cache = {x['symbol']: x for x in top_10}
        last_hourly_update = time.time()
    except: pass

def analyze_symbol(symbol):
    if not is_btc_safe(): return None # منع الدخول إذا كان BTC هابط
    
    # فحص فترة الامتناع
    if symbol in blacklist_cooldown:
        if datetime.now() < blacklist_cooldown[symbol]: return None
        else: del blacklist_cooldown[symbol]

    try:
        h_info = hourly_cache.get(symbol)
        o15 = exchange.fetch_ohlcv(symbol, '15m', limit=20)
        df15 = pd.DataFrame(o15, columns=['t','o','h','l','c','v'])
        cp = df15['c'].iloc[-1]
        
        if cp >= h_info['high_1h']:
            atr = df15['c'].tail(14).diff().abs().mean()
            tp = cp + (atr * 5)
            exp = ((tp - cp) / cp) * 100
            
            if exp >= 4.0:
                # فحص تنويع القطاعات
                current_sectors = [get_sector(s) for s in active_trades.keys()]
                if current_sectors.count(h_info['sector']) >= 2: return None
                
                return {'symbol': symbol, 'price': cp, 'tp': tp, 'sl': cp - (atr * 2.5), 'exp': exp}
    except: return None

# --- 5. التقارير والتشغيل ---

def hourly_reports_loop():
    while True:
        time.sleep(3600)
        report = f"📊 *تقرير الساعة*\n\n✅ صفقات مفتوحة: `{len(active_trades)}`\n"
        if active_trades:
            for s, t in active_trades.items():
                report += f"• `{s}` (دخول: `{t['entry']}`)\n"
        
        report += f"\n📂 مغلق اليوم: `{len(closed_today)}`"
        send_telegram(report)

@app.route('/')
def health(): return "AI Sniper V9 Online", 200

if __name__ == "__main__":
    update_global_cache()
    Thread(target=radar_loop, daemon=True).start() # دالة radar_loop تستخدم analyze_symbol
    Thread(target=monitor_loop, daemon=True).start()
    Thread(target=hourly_reports_loop, daemon=True).start()
    Thread(target=lambda: [(requests.get(SERVER_URL), time.sleep(300)) for _ in iter(int, 1)], daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
