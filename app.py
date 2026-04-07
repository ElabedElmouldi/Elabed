import ccxt
import pandas as pd
import numpy as np
import time
import os
import requests
from threading import Thread
from flask import Flask
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
SERVER_URL = "https://your-app-name.onrender.com" # قم بتحديث هذا بعد الرفع

exchange = ccxt.binance({'enableRateLimit': True})
STABLE_COINS = ['USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'WBTC', 'WETH']

app = Flask(__name__)
virtual_trades = {}
hourly_cache = {} 
last_hourly_update = 0
performance_stats = {"wins": 0, "losses": 0, "total_profit": 0.0}

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. نظام الـ Ping الذاتي (لمنع خمول السيرفر) ---
def keep_alive_ping():
    while True:
        try:
            # إرسال طلب لنفس السيرفر كل 5 دقائق
            requests.get(SERVER_URL, timeout=10)
        except: pass
        time.sleep(300)

# --- 3. تقرير الأداء (كل 6 ساعات) ---
def performance_report():
    while True:
        time.sleep(21600) 
        msg = (f"📊 *تقرير أداء البوت الدوري*\n"
               f"✅ صفقات ناجحة: `{performance_stats['wins']}`\n"
               f"❌ صفقات خاسرة: `{performance_stats['losses']}`\n"
               f"💰 صافي الأرباح: `{performance_stats['total_profit']:.2f}%`\n"
               f"🕒 التوقيت: `{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
        send_telegram(msg)

# --- 4. تحديث بيانات فريم الساعة (الاتجاه العام) ---
def update_hourly_cache():
    global hourly_cache, last_hourly_update
    print("🔄 تحديث فلاتر فريم الساعة...")
    try:
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and s.split('/')[0] not in STABLE_COINS]
        
        for sym in symbols[:150]:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, '1h', limit=30)
                df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
                ema_20 = df['c'].ewm(span=20).mean().iloc[-1]
                
                hourly_cache[sym] = {
                    'bullish': df['c'].iloc[-1] > ema_20,
                    'momentum': ((df['c'].iloc[-1] - df['o'].iloc[-4]) / df['o'].iloc[-4]) * 100
                }
            except: continue
        last_hourly_update = time.time()
    except Exception as e: print(f"Hourly Update Error: {e}")

# --- 5. المحرك الفني (فريم 15 دقيقة) ---
def analyze_symbol(symbol):
    try:
        h_info = hourly_cache.get(symbol)
        if not h_info or not h_info['bullish']: return None

        ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=50)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        
        # S1: قوة السيولة | S2: الاختراق | S5: الضغط
        vol_score = (df['v'].iloc[-1] / df['v'].tail(20).mean()) * 5
        breakout_score = 20 if cp >= df['h'].max() else (cp/df['h'].max())*10
        std = df['c'].tail(15).std()
        compression_score = round(1 / (std / cp + 1e-9), 2)
        
        total_score = vol_score + breakout_score + compression_score + (h_info['momentum'] * 2)
        atr = df['c'].tail(14).diff().abs().mean()
        
        return {'symbol': symbol, 'score': total_score, 'price': cp, 'atr': atr}
    except: return None

# --- 6. مراقبة الصفقات (التتبع والإغلاق) ---
def monitor_trades_loop():
    global performance_stats
    while True:
        try:
            for sym in list(virtual_trades.keys()):
                trade = virtual_trades[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                
                # منطق التتبع (Trailing Stop): تفعيل عند ربح 2%
                if cp > trade['entry'] * 1.02:
                    new_sl = max(trade['sl'], cp * 0.985) # الوقف يلحق السعر بمسافة 1.5%
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                        send_telegram(f"🛡️ *تحديث وقف الربح (تتبع)*\n🪙 `{sym}`\n🔝 الوقف الجديد: `{new_sl:.6f}`")

                # حساب النتيجة الحالية
                res_pct = ((cp - trade['entry']) / trade['entry']) * 100

                # شروط الخروج (الهدف أو الوقف)
                if cp >= trade['tp'] or cp <= trade['sl']:
                    status = "✅ ربح صريح" if cp >= trade['tp'] else "📉 خروج تتبع/وقف"
                    if res_pct > 0: performance_stats['wins'] += 1
                    else: performance_stats['losses'] += 1
                    performance_stats['total_profit'] += res_pct
                    
                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{sym}`\n📈 النتيجة: `{res_pct:+.2f}%` ({status})\n💰 سعر الخروج: `{cp}`")
                    del virtual_trades[sym]
            
            time.sleep(20)
        except Exception as e: print(f"Monitor Error: {e}"); time.sleep(10)

# --- 7. الرادار الرئيسي ---
def radar_loop():
    global last_hourly_update
    send_telegram("🚀 *تم تشغيل نظام Clean Sniper v550 PRO*\n🛡️ التتبع: `مفعل`\n🛰️ السيرفر: `متصل`")
    
    while True:
        try:
            if time.time() - last_hourly_update > 3600: update_hourly_cache()

            tickers = exchange.fetch_tickers()
            targets = [s for s in tickers if s.endswith('/USDT') and s in hourly_cache and 
                       tickers[s].get('quoteVolume', 0) > 15000000][:100]
            
            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(analyze_symbol, targets)))
            
            # فرز ودخول أفضل 3 فرص
            for res in sorted(results, key=lambda x: x['score'], reverse=True)[:3]:
                sym = res['symbol']
                if sym not in virtual_trades and len(virtual_trades) < 5:
                    virtual_trades[sym] = {
                        'entry': res['price'],
                        'tp': res['price'] + (res['atr'] * 4.5), # هدف طموح مع التتبع
                        'sl': res['price'] - (res['atr'] * 2.2),
                        'time': datetime.now()
                    }
                    send_telegram(f"⚡ *إشارة دخول قوية*\n🪙 `{sym}`\n💰 السعر: `{res['price']}`\n🎯 الهدف: `{virtual_trades[sym]['tp']:.6f}`\n🛡️ الوقف: `{virtual_trades[sym]['sl']:.6f}`")

            time.sleep(600) # فحص كل 10 دقائق
        except Exception as e: print(f"Radar Error: {e}"); time.sleep(60)

# --- 8. تشغيل السيرفر ---
@app.route('/')
def health(): return "Bot is running...", 200

if __name__ == "__main__":
    update_hourly_cache()
    # تشغيل الخيوط المتوازية
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_trades_loop, daemon=True).start()
    Thread(target=keep_alive_ping, daemon=True).start()
    Thread(target=performance_report, daemon=True).start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
