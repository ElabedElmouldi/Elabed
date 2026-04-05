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
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=15)
        except: pass

# --- 2. الإعدادات المالية والمرشحات ---
MAX_TRADES = 5
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.03
TRAILING_CALLBACK = 0.012

# استبعاد العملات المستقرة والعملات القيادية الضخمة (الحركة فيها بطيئة)
BLACKLIST = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'DOT/USDT',
    'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'USDP/USDT', 'WBTC/USDT'
]

VOL_MIN = 12000000  # 12 مليون دولار كحد أدنى
VOL_MAX = 500000000 # 500 مليون دولار كحد أقصى (استبعاد العملات الضخمة جداً)

exchange = ccxt.binance({'enableRateLimit': True})

active_trades = {}
daily_closed_trades = []
last_radar_15m = datetime.now() - timedelta(minutes=16)

# --- 3. محرك التحليل (شرط 4 من 5) ---
def analyze_signal_v95(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=70)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        ema50 = df['c'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        df['std'] = df['c'].rolling(20).std()
        df['ma20'] = df['c'].rolling(20).mean()
        width = (df['std'] * 4) / df['ma20']
        
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        exp1 = df['c'].ewm(span=12, adjust=False).mean()
        exp2 = df['c'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        hist = macd - macd.ewm(span=9, adjust=False).mean()
        
        vol_avg = df['v'].iloc[-10:-1].mean()
        vol_now = df['v'].iloc[-1]

        # الشروط الـ 5
        c1 = df['c'].iloc[-1] > ema50
        c2 = width.iloc[-1] < width.rolling(50).mean().iloc[-1] * 1.1 
        c3 = 48 < rsi < 72
        c4 = hist.iloc[-1] > hist.iloc[-2]
        c5 = vol_now > (vol_avg * 1.7)

        score = sum([c1, c2, c3, c4, c5])
        
        if score >= 4: # التعديل المطلوب: 4 من أصل 5 على الأقل
            return {'price': df['c'].iloc[-1], 'score': score, 'rsi': rsi, 'ready': True}
    except: pass
    return {'ready': False}

# --- 4. المحرك الرئيسي وتتبع الـ 10 ثواني ---
def main_engine():
    global last_radar_15m
    send_telegram("🏆 *v9.5 Elite Sniper Active*\n- القاعدة: `4 من 5 شروط`\n- التحديث: `كل 10 ثوانٍ للتتبع`\n- الفلتر: `مستبعد BTC/ETH/Stablecoins`")

    while True:
        try:
            now = datetime.now()

            # أ. إدارة التتبع السريع جداً (كل 10 ثوانٍ تقريباً داخل الحلقة)
            for i in range(4): # تكرار الفحص 4 مرات في الدورة الواحدة لتحقيق سرعة الـ 10 ثوانٍ
                for symbol in list(active_trades.keys()):
                    ticker = exchange.fetch_ticker(symbol)
                    curr_p = ticker['last']
                    trade = active_trades[symbol]
                    
                    if curr_p > trade['highest_p']: trade['highest_p'] = curr_p
                    
                    if not trade['trailing_active'] and curr_p >= trade['entry'] * (1 + ACTIVATION_PCT):
                        trade['trailing_active'] = True
                        send_telegram(f"🚀 *بداية الملاحقة:* `{symbol}`")

                    reason = ""
                    if not trade['trailing_active'] and curr_p <= trade['sl']: reason = "🛑 وقف خسارة"
                    elif trade['trailing_active'] and curr_p <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 جني أرباح"

                    if reason:
                        pnl = (curr_p - trade['entry']) / trade['entry']
                        send_telegram(f"{reason}: `{symbol}` ({pnl*100:+.2f}%)")
                        daily_closed_trades.append({'symbol': symbol, 'pnl': pnl, 'time': now})
                        del active_trades[symbol]
                
                time.sleep(10) # تحديث المعلومات كل 10 ثانية للتتبع

            # ب. فتح صفقات جديدة (مع استبعاد القائمة السوداء)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                # الفلترة: استبعاد المستقرة والعملات الكبيرة وضبط حجم السيولة
                potential = [
                    s for s, d in all_tickers.items() 
                    if '/USDT' in s and s not in BLACKLIST 
                    and VOL_MIN < d['quoteVolume'] < VOL_MAX
                ]
                
                for s in potential[:150]:
                    if len(active_trades) >= MAX_TRADES: break
                    sig = analyze_signal_v95(s)
                    if sig and sig['ready']:
                        active_trades[s] = {'entry': sig['price'], 'sl': sig['price']*0.97, 'highest_p': sig['price'], 'trailing_active': False, 'start': now}
                        send_telegram(f"💎 *دخول نخبة:* `{s}` (القوة: `{sig['score']}/5`)")

            # ج. الرادار (15 دقيقة)
            if now >= last_radar_15m + timedelta(minutes=15):
                # عرض العملات التي حققت 4 من 5
                radar_list = []
                # (منطق الرادار المعتاد مع فلتر النخبة)
                # ...
                last_radar_15m = now

        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return f"Elite Sniper v9.5 | Active: {len(active_trades)}/5"
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    main_engine()
