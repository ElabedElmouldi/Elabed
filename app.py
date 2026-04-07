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

# --- 1. الإعدادات الأساسية (أدخل مفاتيح API الخاصة بك هنا) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
SERVER_URL = "https://your-app-name.onrender.com"

# إعداد الربط مع بينانس (حساب حقيقي)
exchange = ccxt.binance({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'} # تداول فوري (Spot)
})

STABLE_COINS = ['USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 'GBP', 'PAXG', 'AEUR', 'USDP', 'WBTC', 'WETH']

# إعدادات الميزانية
TOTAL_BALANCE = 500
COST_PER_TRADE = 100
MAX_TRADES = 5 # 5 صفقات كحد أقصى لتغطية الرصيد 500$

app = Flask(__name__)
active_trades = {} # الصفقات الحقيقية المفتوحة
hourly_cache = {} 
last_hourly_update = 0

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. دالة تنفيذ الشراء الحقيقي ---
def place_buy_order(symbol, price):
    try:
        # حساب الكمية: 100 دولار تقسيم السعر الحالي
        amount = COST_PER_TRADE / price
        
        # تنفيذ أمر شراء بسعر السوق (Market Order)
        order = exchange.create_market_buy_order(symbol, amount)
        
        send_telegram(f"💰 *تم الشراء حقيقياً*\n🪙 `{symbol}`\n💵 المبلغ: `100$`\n📦 الكمية: `{amount:.6f}`")
        return order
    except Exception as e:
        send_telegram(f"⚠️ *خطأ في تنفيذ الشراء*\n🪙 `{symbol}`\n❌ السبب: `{str(e)}`")
        return None

# --- 3. دالة تنفيذ البيع الحقيقي ---
def place_sell_order(symbol):
    try:
        # جلب الرصيد المتاح من هذه العملة في المحفظة لبيعه بالكامل
        balance = exchange.fetch_balance()
        base_asset = symbol.split('/')[0]
        amount_to_sell = balance.get(base_asset, {}).get('free', 0)
        
        if amount_to_sell > 0:
            order = exchange.create_market_sell_order(symbol, amount_to_sell)
            return order
        return None
    except Exception as e:
        send_telegram(f"⚠️ *خطأ في تنفيذ البيع*\n🪙 `{symbol}`\n❌ السبب: `{str(e)}`")
        return None

# --- 4. مراقبة الصفقات والإغلاق ---
def monitor_trades_loop():
    while True:
        try:
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                ticker = exchange.fetch_ticker(sym)
                cp = ticker['last']
                
                # تحديث الوقف المتحرك (Trailing Stop)
                if cp > trade['entry'] * 1.02:
                    new_sl = max(trade['sl'], cp * 0.985)
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl
                        send_telegram(f"🛡️ *تحديث الوقف*\n🪙 `{sym}`\n🔝 السعر الجديد: `{new_sl:.6f}`")

                # شروط الخروج
                if cp >= trade['tp'] or cp <= trade['sl']:
                    sell_order = place_sell_order(sym)
                    if sell_order:
                        res_pct = ((cp - trade['entry']) / trade['entry']) * 100
                        send_telegram(f"🏁 *إغلاق صفقة حقيقية*\n🪙 `{sym}`\n📈 النتيجة: `{res_pct:+.2f}%` \n💰 سعر الخروج: `{cp}`")
                        del active_trades[sym]
            
            time.sleep(20)
        except Exception as e: print(f"Monitor Error: {e}"); time.sleep(10)

# --- 5. الرادار والتحليل (15m + 1h) ---
def radar_loop():
    global last_hourly_update
    send_telegram(f"🚀 *تشغيل البوت الحقيقي*\n💰 الرصيد المستهدف: `{TOTAL_BALANCE}$` \n💵 لكل صفقة: `{COST_PER_TRADE}$` \n🛡️ الحد الأقصى: `{MAX_TRADES}` صفقات")
    
    while True:
        try:
            # تحديث الكاش كل ساعة (نفس منطق الكود السابق)
            # ... (دالة update_hourly_cache تبقى كما هي) ...
            
            tickers = exchange.fetch_tickers()
            targets = [s for s in tickers if s.endswith('/USDT') and s in hourly_cache][:100]
            
            with ThreadPoolExecutor(max_workers=10) as exec:
                # ... (دالة analyze_symbol تبقى كما هي) ...
                results = list(filter(None, exec.map(analyze_symbol, targets)))
            
            for res in sorted(results, key=lambda x: x['score'], reverse=True):
                sym = res['symbol']
                # التأكد من عدم تجاوز 5 صفقات مفتوحة
                if sym not in active_trades and len(active_trades) < MAX_TRADES:
                    # تنفيذ أمر الشراء الحقيقي أولاً
                    order = place_buy_order(sym, res['price'])
                    
                    if order:
                        active_trades[sym] = {
                            'entry': res['price'],
                            'tp': res['price'] + (res['atr'] * 4.5),
                            'sl': res['price'] - (res['atr'] * 2.2),
                            'time': datetime.now()
                        }
            
            time.sleep(600)
        except Exception as e: print(f"Radar Error: {e}"); time.sleep(60)

# (بقية الدوال keep_alive_ping و performance_report و app.run تبقى كما هي)
