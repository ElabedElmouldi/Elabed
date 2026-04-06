import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات والروابط ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

# إعداد المنصة
exchange = ccxt.binance({
    'enableRateLimit': True, 
    'options': {'defaultType': 'spot'}
})

# إعدادات الاستراتيجية
MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03 
TRAILING_GAP = 0.01      
STOP_LOSS_PCT = 0.035    

active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def get_wallet_balance():
    """جلب رصيد المحفظة الإجمالي والمتاح"""
    try:
        balance = exchange.fetch_balance()
        return balance['total'].get('USDT', 0), balance['free'].get('USDT', 0)
    except: return 0, 0

# --- 2. محرك المسح وإرسال قائمة أفضل 10 عملات ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🚀 *تم تفعيل رادار النخبة v28.0*\nجاري فحص 900 عملة وإرسال التقرير الدوري...")
    
    while True:
        try:
            now = datetime.now()
            # تنظيف القائمة السوداء
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            # جلب بيانات السوق
            tickers = exchange.fetch_tickers()
            all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
            # اختيار أعلى 900 عملة من حيث السيولة
            targets = sorted(all_symbols, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:900]
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    t = tickers[s]
                    score = 0
                    change = t.get('percentage', 0)
                    vol = t.get('quoteVolume', 0)
                    if vol > 2000000: score += 10
                    if change > 2.0: score += 10
                    if score >= 10:
                        return {'symbol': s, 'score': score, 'price': t['last'], 'change': change}
                return None

            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(executor.map(process_scan, targets))
                candidates = [r for r in results if r]

            # ترتيب القائمة (الأقوى أولاً)
            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # تحديث منطق الصدارة الثلاثي للدخول التلقائي
            if top_10:
                current_winner = top_10[0]['symbol']
                if current_winner == leaderboard_tracker["symbol"]:
                    leaderboard_tracker["count"] += 1
                else:
                    leaderboard_tracker["symbol"] = current_
