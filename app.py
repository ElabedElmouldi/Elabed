import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

# إعدادات الاستراتيجية (تعديل الأهداف)
MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03   # تفعيل التتبع عند ربح 3%
TRAILING_GAP = 0.01        # فارق التتبع 1%
STOP_LOSS_PCT = 0.035      # وقف خسارة 3.5%
MIN_DISTANCE_FROM_RES = 0.02 # مسافة أمان من المقاومة 2%

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك التحليل الفني (بدون مكتبات خارجية) ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def get_resistance_level(symbol):
    """جلب أعلى قمة في آخر 100 ساعة لفلترة الدخول عند القمم"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        return df['h'].max()
    except: return 0

def calculate_total_score(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        score = 0
        curr_p = df['c'].iloc[-1]
        
        # 1. RSI (5 نقاط) - البحث عن بداية الزخم
        df['rsi'] = calculate_rsi(df['c'])
        rsi = df['rsi'].iloc[-1]
        if 50 < rsi < 65: score += 5
        elif 65 <= rsi < 75: score += 3
        
        # 2. المتوسطات EMA (5 نقاط) - تأكيد الاتجاه الصاعد
        df['ema20'] = calculate_ema(df['c'], 20)
        df['ema50'] = calculate_ema(df['c'], 50)
        if curr_p > df['ema20'].iloc[-1] > df['ema50'].iloc[-1]: score += 5
        
        # 3. الحجم (5 نقاط) - رصد دخول الحيتان
        avg_v = df['v'].tail(20).mean()
        if df['v'].iloc[-1] > avg_v * 1.8: score += 5
        
        # 4. الزخم اللحظي (5 نقاط)
        chg = ((curr_p - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 1.5 < chg < 5.0: score += 5
        
        return score, curr_p, chg
    except: return 0, 0, 0

# --- 3. المحرك الرئيسي (مسح كل 5 دقائق لـ 500 عملة) ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🚀 *قناص بايننس v36.0 متصل*\n⏱️ نظام المسح: كل 5 دقائق\n🎯 النطاق: أقوى 500 زوج USDT")
    
    while True:
        try:
            now = datetime.now()
            # تنظيف القائمة السوداء
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            # جلب وتصفية أفضل 500 عملة من حيث السيولة
            markets = exchange.fetch_markets()
            all_usdt = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['spot']]
            tickers = exchange.fetch_tickers(all_usdt)
            sorted_symbols = sorted(all_usdt, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:500]
            
            candidates = []
            def process_scan(s):
                if s not
