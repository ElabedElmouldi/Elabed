import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# --- 2. الإعدادات المالية والفلاتر ---
MAX_TRADES = 5
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

# استبعاد العملات المستقرة والقيادية الضخمة
BLACKLIST = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'USDC/USDT', 'FDUSD/USDT', 'USDT/DAI', 'DAI/USDT']
VOL_MIN = 12000000
VOL_MAX = 450000000

# إعداد المنصة مع وقت انتظار طويل لتجنب التوقف
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'timeout': 30000
})

active_trades = {}
daily_closed_trades = []

# مواقيت التقارير
last_radar_15m = datetime.now() - timedelta(minutes=16)
last_open_report_1h = datetime.now()
last_closed_report_6h = datetime.now()

# --- 3. محرك التحليل العشاري المطور (المعيار 7/10) ---
def analyze_signal(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        close = df['c']
        high = df['h']
        low = df['l']
        volume = df['v']

        # 1. الاتجاه (EMA 50)
        ema50 = close.ewm(span=50, adjust=False).mean()
        # 2. الانضغاط (Bollinger Bands)
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_width = (std20 * 4) / ma20
        # 3. الزخم (RSI)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        # 4. الماكد (MACD)
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_h = macd_line - signal_line
        # 5. السيولة
        vol_avg = volume.iloc[-15:-1].mean()
        # 6. المتوسط السريع (EMA 20)
        ema20 = close.ewm(span=20, adjust=False).mean()
        # 7. قوة الاتجاه (ADX مبسط)
        tr = (high - low).rolling(14).mean()
        plus_dm = high.diff().clip(lower=0).rolling(14).mean()
        adx_val = (plus_dm / tr.replace(0, 0.001) * 100)
        # 8. التذبذب (ATR)
        atr_avg = tr.rolling(50).mean()

        score = 0
        if close.iloc[-1] > ema50.iloc[-1]: score += 1                # 1
        if bb_width.iloc[-1] < bb_width.rolling(50).mean().iloc[-1]: score += 1 # 2
        if 48 < rsi.iloc[-1] < 70: score += 1                        # 3
        if macd_h.iloc[-1] > macd_h.iloc[-2]: score += 1              # 4
        if volume.iloc[-1] > vol_avg * 1.6: score += 1               # 5
        if ema20.iloc[-1] > ema50.iloc[-1]: score += 1               # 6
        if close.iloc[-1] > df['o'].iloc[-1]: score += 1             # 7
        if adx_val.iloc[-1] > 22: score += 1                         # 8
        if tr.iloc[-1] > atr_avg.iloc[-1]: score += 1                # 9
        if rsi.iloc[-1] > 55: score += 1                             # 10

        if score >= 7:
            return {'price': close.iloc[-1], 'score': score, 'rsi': rsi.iloc[-1], 'ready': True}
    except Exception: pass
    return {'ready': False}

# --- 4. المحرك التنفيذي (التتبع والتقارير) ---
def main_engine():
    global last_radar_15m, last_open_report_1h, last_closed_report_6h
    send_telegram("🚀 *v10.2 Ultra Sniper Fix*\n- المعيار: `7/10 نقاط`\n- التحديث: `10 ثوانٍ` ⏱️\n- النظام: `جاهز للعمل`")

    while True:
        try:
            now = datetime.now()

            # أ. حلقة التتبع فائقة السرعة (6 مرات في الدقيقة)
            for _ in range(6):
                for symbol in list(active_trades.keys()):
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        curr_p = ticker['last']
                        trade = active_trades[symbol]
                        
                        if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                        
                        if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                            trade['trailing_active'] = True
                            send_telegram(f"🎯 *Target Hit:* `{symbol}` دخلت الملاحقة.")

                        reason = ""
                        if not trade['trailing_active'] and curr_p <= trade['sl']: reason = "🛑 SL"
                        elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 TP"

                        if reason:
                            pnl = (curr_p - trade['entry']) / trade['entry']
                            dur = str(now - trade['start']).split('.')[0]
                            send_telegram(f"{reason}: `{symbol}`\n📊 الربح: `{pnl*100:+.2f}%`\n⏱️ المدة: `{dur}`")
                            daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'time': now, 'dur': dur})
                            del active_trades[symbol]
                    except: continue
                time.sleep(10) # شرط الـ 10 ثوانٍ

            # ب. البحث عن صفقات جديدة (5 صفقات)
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                for s in potential[:100]:
                    if len(active_trades) >= MAX_TRADES: break
                    sig = analyze_signal(s)
                    if sig and sig['ready']:
                        active_trades[s] = {'entry': sig['price'], 'sl': sig['price']*0.97, 'highest_p': sig['price'], 'trailing_active': False, 'start': now}
                        send_telegram(f"💎 *Entry ({sig['score']}/10):* `{s}` بسعر `{sig['price']}`")

            # ج. معالجة التقارير المجدولة
            if now >= last_radar_15m + timedelta(minutes=15):
                send_telegram(f"📡 *Radar Check:* السوق مستقر حالياً. صفقات نشطة: `{len(active_trades)}/5
