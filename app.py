import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية (نظام الـ 5 صفقات × 100$) ---
MAX_TRADES = 5
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

# استبعاد العملات الثقيلة والمستقرة
BLACKLIST = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'USDC/USDT', 'FDUSD/USDT', 'USDT/DAI']
VOL_MIN = 12000000
VOL_MAX = 450000000

exchange = ccxt.binance({'enableRateLimit': True})
active_trades = {}
daily_closed_trades = []

# مواقيت التقارير
last_radar_15m = datetime.now() - timedelta(minutes=16)
last_open_report_1h = datetime.now()
last_closed_report_6h = datetime.now()

# --- 3. خوارزمية التحليل العشاري (المعيار 7/10) ---
def analyze_signal_v10_1(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # تجهيز البيانات
        close = df['c']
        high = df['h']
        low = df['l']
        volume = df['v']

        # المؤشرات العشرة:
        # 1. الاتجاه (EMA 50)
        ema50 = close.ewm(span=50).mean().iloc[-1]
        # 2. الانضغاط (BB Width)
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_width = (std20 * 4) / ma20
        # 3. الزخم (RSI)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        # 4. الماكد (MACD Histogram)
        exp12 = close.ewm(span=12).mean()
        exp26 = close.ewm(span=26).mean()
        macd_h = (exp12 - exp26) - (exp12 - exp26).ewm(span=9).mean()
        # 5. السيولة (Volume Factor)
        vol_avg = volume.iloc[-15:-1].mean()
        # 6. التقاطع الذهبي (EMA 20/50)
        ema20 = close.ewm(span=20).mean().iloc[-1]
        # 7. الحركة السعرية (Bullish Candle)
        is_bullish = close.iloc[-1] > df['o'].iloc[-1]
        # 8. قوة الاتجاه (ADX تقريبي)
        plus_dm = high.diff().clip(lower=0).rolling(14).mean()
        tr = (high - low).rolling(14).mean()
        adx_val = (plus_dm / tr * 100).iloc[-1]
        # 9. تزايد التذبذب (ATR)
        atr_now = tr.iloc[-1]
        atr_avg = tr.rolling(50).mean().iloc[-1]
        # 10. تشبع البيع (Stochastic RSI)
        stoch_k = (rsi - 20) / 60 

        # حساب النقاط (Score)
        score = 0
        if close.iloc[-1] > ema50: score += 1               # 1. فوق الاتجاه
        if bb_width.iloc[-1] < bb_width.rolling(50).mean().iloc[-1] * 1.1: score += 1 # 2. انضغاط
        if 48 < rsi < 70: score += 1                        # 3. زخم مثالي
        if macd_h.iloc[-1] > macd_h.iloc[-2]: score += 1     # 4. تسارع صاعد
        if volume.iloc[-1] > vol_avg * 1.6: score += 1      # 5. دخول سيولة
        if ema
