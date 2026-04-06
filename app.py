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
        except: pass

# --- 2. الإعدادات المالية ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.03
MAX_24H_CHANGE = 0.10

BLACKLIST = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT',
    'USDC/USDT', 'FDUSD/USDT', 'USDP/USDT', 'TUSD/USDT', 'DAI/USDT', 'EUR/USDT', 
    'USD1/USDT', 'USDE/USDT', 'PYUSD/USDT', 'USTC/USDT', 'BUSD/USDT', 'AEUR/USDT',
    'WBTC/USDT', 'WETH/USDT', 'PAXG/USDT'
]

VOL_MIN = 10000000 
VOL_MAX = 400000000 

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}
last_report_15m = datetime.now()

def get_indicators(df):
    close = df['c']
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss.replace(0, 0.1))))
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()
    return ema50, ema20, rsi, macd, signal

def analyze_logic(symbol, change_24h):
    if change_24h >= MAX_24H_CHANGE: return None
    try:
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
        df_1h = pd.DataFrame(bars_1h, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_1h, _, _, _, _ = get_indicators(df_1h)

        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df_15m = pd.DataFrame(bars_15m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_15m, ema20_15m, rsi_15m, macd, macd_sig = get_indicators(df_15m)

        # الشروط الإلزامية
        if df_1h['c'].iloc[-1] <= ema50_1h.iloc[-1]: return None
        vol_avg = df_15m['v'].iloc[-20:-1].mean()
        if df_15m['v'].iloc[-1] < vol_avg * 1.5: return None

        score = 0
        if rsi_15m.iloc[-1] > 50: score += 1
        if df_15m['c'].iloc[-1] > ema20_15m.iloc[-1]: score += 1
        if 48 < rsi_15m.iloc[-1] < 70: score += 1
        if macd.iloc[-1] > macd_sig.iloc[-1]: score += 1
        if ema20_15m.iloc[-1] > ema50_15m.iloc[-1]: score += 1
        if df_15m['c'].iloc[-1] > df_15m['o'].iloc[-1]: score += 1
        if rsi_15m.iloc[-1] > rsi_15m.iloc[-2]: score += 1
        if df_1h['c'].iloc[-1] > df_1h['o'].iloc[-1]: score += 1

        return score + 2 if score >= 5 else None
    except: return None

# --- 3. تقارير الـ 15 دقيقة وقائمة الانفجار ---
def send_15m_detailed_report():
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['free']['USDT']
        total_used = len(active_trades) * TRADE_AMOUNT
        
        # أ. حساب PNL العائم
        unrealized_pnl = 0
        active_list = ""
        for s, d in active_trades.items():
            cp = exchange.fetch_ticker(s)['last']
            p = (cp - d['entry']) / d['entry']
            unrealized_pnl += (p * TRADE_AMOUNT)
            active_list += f"🔸 `{s}`: `{p*100:+.2f}%`\n"

        # ب. البحث عن عملات "قابلة للانفجار" الآن
        tickers = exchange.fetch_tickers()
        scout_list = []
        potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
        
        for s in potential[:60]: # فحص سريع لأفضل 60 عملة سيولة
            score = analyze_logic(s, tickers[s]['percentage']/100)
            if score: scout_list.append((s, score))
        
        scout_list = sorted(scout_list, key=lambda x: x[1], reverse=True)[:3]
        scout_text = ""
        for s, score in scout_list:
            scout_text += f"🚀 `{s}` (قوة الإشارة: `{score}/10`)\n"

        report = (
            f"🕒 *تقرير الـ 15 دقيقة (v12.2)*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 *الرصيد المتاح:* `{free_usdt:.2f}$` \n"
            f"🏗️ *الرصيد المستعمل:* `{total_used:.2f}$` \n"
            f"📈 *الربح العائم:* `{unrealized_pnl:+.2f}$` \n"
            f"━━━━━━━━━━━━━━\n"
            f"📑 *الصفقات النشطة ({len(active_trades)}):*\n{active_list if active_list else 'لا يوجد'}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔥 *مرشحة للانفجار الآن:*\n{scout_text if scout_text else 'جاري البحث...'}"
        )
        send_telegram(report)
    except: pass

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_report_15m
    send_telegram("🛰️ *High-Frequency Scout v12.2 Active*\n- تقارير شاملة كل 15 دقيقة\n- نظام رصد الانفجار السعري")

    while True:
        try:
            now = datetime.now()

            # التتبع والبيع (كل 10 ثوانٍ)
            for _ in range(6):
                for symbol in list(active_trades.keys()):
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        cp = ticker['last']
                        pnl = (cp - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                        
                        if pnl >= TAKE_PROFIT_PCT:
                            send_telegram(f"💰 *تم جني الربح:* `{symbol}` (+3%)")
                            del active_trades[symbol]
                        elif pnl <= -STOP_LOSS_PCT:
                            send_telegram(f"🛑 *ضرب الوقف:* `{symbol}` (-3%)")
                            del active_trades[symbol]
                    except: continue
                time.sleep(10)

            # فتح صفقات جديدة
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                for s in potential[:100]:
                    if s in active_trades: continue
                    if len(active_trades) >= MAX_TRADES: break
                    score = analyze_logic(s, tickers[s]['percentage']/100)
                    if score:
                        entry_p = exchange.fetch_ticker(s)['last']
                        active_trades[s] = {'entry': entry_p, 'start_dt': now}
                        send_telegram(f"💎 *فتح صفقة (100$):* `{s}`\nسعر الدخول: `{entry_p}`")

            # إرسال التقرير كل 15 دقيقة
            if now >= last_report_15m + timedelta(minutes=15):
                send_15m_detailed_report()
                last_report_15m = now

        except: time.sleep(15)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Bot v12.2 15m Reporting Active"
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
