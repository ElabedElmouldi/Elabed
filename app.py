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
exchange = ccxt.binance({'enableRateLimit': True})

STABLE_COINS = ['USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'WBTC', 'WETH']

app = Flask(__name__)
virtual_trades = {}

# مخزن البيانات للفريمات الكبيرة (1h) لتقليل الضغط على API
hourly_cache = {} 
last_hourly_update = 0

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك تحديث البيانات الكبيرة (مرة كل ساعة) ---

def update_hourly_data():
    """تحديث مؤشرات فريم الساعة لجميع العملات النشطة"""
    global hourly_cache, last_hourly_update
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Updating Hourly Trend Cache...")
    try:
        tickers = exchange.fetch_tickers()
        # نركز على العملات ذات السيولة المقبولة فقط
        symbols = [s for s in tickers if s.endswith('/USDT') and 
                   s.split('/')[0] not in STABLE_COINS and 
                   tickers[s].get('quoteVolume', 0) > 5000000]

        for sym in symbols[:150]: # فحص أعلى 150 عملة
            try:
                ohlcv = exchange.fetch_ohlcv(sym, '1h', limit=50)
                df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
                
                # S3: الاتجاه (السعر فوق EMA 20)
                ema_20 = df['c'].ewm(span=20).mean().iloc[-1]
                is_bullish = df['c'].iloc[-1] > ema_20
                
                # S4: قوة التغيير خلال آخر 4 ساعات
                change_4h = ((df['c'].iloc[-1] - df['o'].iloc[-4]) / df['o'].iloc[-4]) * 100
                
                hourly_cache[sym] = {
                    'bullish_1h': is_bullish,
                    'momentum_1h': round(change_4h * 4, 2),
                    'high_1h': df['h'].max()
                }
            except: continue
        
        last_hourly_update = time.time()
        print(f"✅ Cache Updated: {len(hourly_cache)} symbols stored.")
    except Exception as e:
        print(f"Error in Hourly Update: {e}")

# --- 3. المحرك الفني (فريم 15 دقيقة) ---

def get_scores(symbol):
    try:
        if symbol.split('/')[0] in STABLE_COINS: return None
        
        # التأكد من وجود بيانات الساعة للعملة
        h_data = hourly_cache.get(symbol)
        if not h_data or not h_data['bullish_1h']: return None

        # جلب بيانات 15 دقيقة للتحليل اللحظي
        ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        
        # S1: السيولة اللحظية (15m)
        s1 = round((df['v'].iloc[-1] / df['v'].tail(20).mean()) * 5, 2)
        
        # S2: الاختراق (15m) - مقارنة السعر بقمة الـ 15 دقيقة
        s2 = round(20 if cp >= df['h'].max() else (cp/df['h'].max())*10, 2)
        
        # S3 & S4: من بيانات الساعة المخزنة
        s3 = 15 # بما أننا تجاوزنا شرط h_data['bullish_1h'] أعلاه
        s4 = h_data['momentum_1h']
        
        # S5: الضغط (15m) - انخفاض التذبذب قبل الانفجار
        std = df['c'].tail(20).std()
        s5 = round(1 / (std / cp + 1e-9), 2)
        
        # ATR لحساب الأهداف (15m)
        atr = df['c'].tail(14).diff().abs().mean() 
        
        return {
            'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 
            'total': s1+s2+s3+s4+s5, 'price': cp, 'atr': atr
        }
    except: return None

# --- 4. إدارة العمليات والرادار ---

def radar_loop():
    global last_hourly_update
    send_telegram("🛡️ *Clean Sniper v540 PRO*\nتفعيل نظام الفريمات المزدوجة (15m & 1h)")
    
    while True:
        try:
            # تحديث الكاش كل ساعة
            if time.time() - last_hourly_update > 3600:
                update_hourly_data()

            tickers = exchange.fetch_tickers()
            targets = [s for s in tickers if s.endswith('/USDT') and 
                       s in hourly_cache and 
                       tickers[s].get('quoteVolume', 0) > 15000000][:120]
            
            with ThreadPoolExecutor(max_workers=15) as exec:
                results = list(filter(None, exec.map(get_scores, targets)))
            
            # فلترة القوائم الذكية
            L1 = {r['symbol'] for r in sorted(results, key=lambda x: x['s1'], reverse=True)[:10]}
            L2 = {r['symbol'] for r in sorted(results, key=lambda x: x['s2'], reverse=True)[:10]}
            
            # شرط دخول صارم: L1 + L2 + اتجاه ساعة صاعد
            qualified = [r for r in results if r['symbol'] in L1 and r['symbol'] in L2]

            for data in qualified:
                sym = data['symbol']
                if sym not in virtual_trades and len(virtual_trades) < 5:
                    atr = data['atr']
                    virtual_trades[sym] = {
                        'entry': data['price'], 
                        'tp': data['price'] + (atr * 3.5), # زيادة الهدف قليلاً لتماشيه مع الاتجاه العام
                        'sl': data['price'] - (atr * 2), 
                        'time': datetime.now()
                    }
                    send_telegram(f"🚀 *إشارة دخول ذهبية*\n🪙 `{sym}`\n📈 الاتجاه (1h): `صاعد ✅`\n⚡ السيولة (15m): `عالية 🔥`\n💰 السعر: `{data['price']}`\n🎯 الهدف: `{virtual_trades[sym]['tp']:.6f}`")

            time.sleep(600) # فحص كل 10 دقائق
        except Exception as e:
            print(f"Radar Error: {e}"); time.sleep(60)

# (دالة monitor_loop تبقى كما هي لإدارة الصفقات المفتوحة)

if __name__ == "__main__":
    # تحديث أولي للكاش قبل بدء الرادار
    update_hourly_data()
    
    Thread(target=radar_loop, daemon=True).start()
    # Thread(target=monitor_loop, daemon=True).start() # قم بتفعيلها عند إضافة كود المراقبة
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
