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

# --- 2. الإعدادات المالية الجديدة (10 صفقات × 100$) ---
MAX_TRADES = 10
TRADE_AMOUNT = 100 # مبلغ كل صفقة
STOP_LOSS_PCT = 0.03
ACTIVATION_PCT = 0.025
TRAILING_CALLBACK = 0.01
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
last_report_time = datetime.now()

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

def analyze_v12(symbol, change_24h):
    if change_24h >= MAX_24H_CHANGE: return {'ready': False}
    try:
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=60)
        df_1h = pd.DataFrame(bars_1h, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_1h, _, _, _, _ = get_indicators(df_1h)

        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df_15m = pd.DataFrame(bars_15m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema50_15m, ema20_15m, rsi_15m, macd, macd_sig = get_indicators(df_15m)

        # الشروط الإلزامية
        if df_1h['c'].iloc[-1] <= ema50_1h.iloc[-1]: return {'ready': False}
        vol_avg = df_15m['v'].iloc[-20:-1].mean()
        if df_15m['v'].iloc[-1] < vol_avg * 1.5: return {'ready': False}

        score = 0
        if rsi_15m.iloc[-1] > 50: score += 1
        if df_15m['c'].iloc[-1] > ema20_15m.iloc[-1]: score += 1
        if 48 < rsi_15m.iloc[-1] < 70: score += 1
        if macd.iloc[-1] > macd_sig.iloc[-1]: score += 1
        if ema20_15m.iloc[-1] > ema50_15m.iloc[-1]: score += 1
        if df_15m['c'].iloc[-1] > df_15m['o'].iloc[-1]: score += 1
        if rsi_15m.iloc[-1] > rsi_15m.iloc[-2]: score += 1
        if df_1h['c'].iloc[-1] > df_1h['o'].iloc[-1]: score += 1

        if score >= 5:
            return {'price': df_15m['c'].iloc[-1], 'score': score + 2, 'ready': True}
    except: pass
    return {'ready': False}

# --- 3. نظام تقارير المحفظة ---
def send_portfolio_report():
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['free']['USDT']
        
        total_used = len(active_trades) * TRADE_AMOUNT
        unrealized_pnl_usd = 0
        trades_details = ""

        for symbol, data in active_trades.items():
            current_price = exchange.fetch_ticker(symbol)['last']
            pnl_pct = (current_price - data['entry']) / data['entry']
            pnl_usd = TRADE_AMOUNT * pnl_pct
            unrealized_pnl_usd += pnl_usd
            trades_details += f"🔸 `{symbol}`: `{pnl_pct*100:+.2f}%` (`{pnl_usd:+.2f}$`)\n"

        total_wallet_value = free_usdt + total_used + unrealized_pnl_usd

        report = (
            f"📊 *تقرير المحفظة الساعي (v12.0)*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 *الرصيد الكلي:* `{total_wallet_value:.2f}$` \n"
            f"💵 *رصيد متاح (Free):* `{free_usdt:.2f}$` \n"
            f"🏗️ *رصيد مستعمل:* `{total_used:.2f}$` \n"
            f"📈 *أرباح/خسائر عائمة:* `{unrealized_pnl_usd:+.2f}$` \n"
            f"━━━━━━━━━━━━━━\n"
            f"📑 *الصفقات النشطة ({len(active_trades)}/{MAX_TRADES}):*\n"
            f"{trades_details if trades_details else 'لا توجد صفقات حالياً'}"
        )
        send_telegram(report)
    except Exception as e:
        print(f"Report Error: {e}")

# --- 4. المحرك التنفيذي ---
def main_engine():
    global last_report_time
    send_telegram("🚀 *v12.0 Deployed Successfully*\n- نظام 10 صفقات × 100$\n- تقارير المحفظة: نشطة كل ساعة")

    while True:
        try:
            now = datetime.now()

            # أ. التتبع السريع (كل 10 ثوانٍ)
            for _ in range(6):
                for symbol in list(active_trades.keys()):
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        cp = ticker['last']
                        trade = active_trades[symbol]
                        if cp > trade['highest_p']: trade['highest_p'] = cp
                        
                        if not trade['trailing_active'] and cp >= trade['entry'] * (1 + ACTIVATION_PCT):
                            trade['trailing_active'] = True
                            send_telegram(f"⚡ *Trailing:* `{symbol}`")

                        reason = ""
                        if not trade['trailing_active'] and cp <= trade['sl']: reason = "🛑 SL"
                        elif trade['trailing_active'] and cp <= trade['highest_p'] * (1 - TRAILING_CALLBACK): reason = "💰 TP"

                        if reason:
                            pnl = (cp - trade['entry']) / trade['entry']
                            send_telegram(f"{reason}: `{symbol}` ({pnl*100:+.2f}%)")
                            del active_trades[symbol]
                    except: continue
                time.sleep(10)

            # ب. فتح صفقات جديدة (بشرط توفر رصيد)
            if len(active_trades) < MAX_TRADES:
                tickers = exchange.fetch_tickers()
                potential = [s for s, d in tickers.items() if '/USDT' in s and s not in BLACKLIST and VOL_MIN < d['quoteVolume'] < VOL_MAX]
                
                for s in potential[:100]:
                    if s in active_trades: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    sig = analyze_v12(s, tickers[s]['percentage']/100)
                    if sig and sig['ready']:
                        entry_p = sig['price']
                        active_trades[s] = {
                            'entry': entry_p, 'sl': entry_p * (1 - STOP_LOSS_PCT), 
                            'highest_p': entry_p, 'trailing_active': False, 
                            'start_dt': now
                        }
                        send_telegram(f"💎 *Entry Verified (100$)*\n🪙 `{s}` | 💵 `{entry_p}`")

            # ج. إرسال التقرير الشامل كل ساعة
            if now >= last_report_time + timedelta(hours=1):
                send_portfolio_report()
                last_report_time = now

        except: time.sleep(15)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Bot v12.0 Active"
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main_engine()
