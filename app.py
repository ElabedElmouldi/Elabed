import ccxt
import pandas as pd
import time
from datetime import datetime
from flask import Flask
from threading import Thread

# --- إعداد خادم ويب صغير لمنع Render من النوم ---
app = Flask('')

@app.route('/')
def home():
    return "البوت نشط ويعمل 24/7"

def run_web_server():
    # Render يتطلب المنفذ 10000 أو يتم تحديده عبر البيئة
    app.run(host='0.0.0.0', port=10000)

# --- كود البوت الأساسي ---
exchange = ccxt.binance({'enableRateLimit': True})

VIRTUAL_BALANCE = 100.0
INITIAL_BALANCE = 100.0
PERCENT_PER_TRADE = 0.20
MAX_TRADES = 5
TARGET_PROFIT = 1.04
STOP_LOSS = 0.98
MIN_VOLUME = 10000000

active_trades = []
trade_history = []

def get_top_gainers(limit=100):
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT']
        for symbol, data in tickers.items():
            if '/USDT' in symbol and symbol not in exclude:
                if data['quoteVolume'] > MIN_VOLUME:
                    gainers.append({
                        'symbol': symbol,
                        'percentage': data['percentage'],
                        'volume': data['quoteVolume']
                    })
        gainers.sort(key=lambda x: x['percentage'], reverse=True)
        return [item['symbol'] for item in gainers[:limit]]
    except: return []

def get_indicators(symbol):
    try:
        time.sleep(0.2) # تأخير إضافي للأمان
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        df['ma'] = df['close'].rolling(window=20).mean()
        return df.iloc[-1]
    except: return None

def run_trading_logic():
    global VIRTUAL_BALANCE
    print("🚀 انطلاق البوت في بيئة Render...")
    
    while True:
        try:
            symbols = get_top_gainers(limit=100)
            
            if len(active_trades) < MAX_TRADES:
                entry_amount = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    data = get_indicators(symbol)
                    if data is not None and data['rsi'] <= 45 and data['close'] <= data['ma']:
                        new_trade = {
                            'symbol': symbol,
                            'entry_price': data['close'],
                            'target': data['close'] * TARGET_PROFIT,
                            'stop': data['close'] * STOP_LOSS,
                            'cost': entry_amount
                        }
                        active_trades.append(new_trade)
                        VIRTUAL_BALANCE -= entry_amount
                        print(f"🔔 [دخول] {symbol} | السعر: {new_trade['entry_price']}")

            if active_trades:
                tickers = exchange.fetch_tickers()
                for trade in active_trades[:]:
                    p_now = tickers[trade['symbol']]['last']
                    if p_now >= trade['target']:
                        VIRTUAL_BALANCE += (trade['cost'] * TARGET_PROFIT)
                        print(f"💰 [ربح] {trade['symbol']} | الرصيد: {VIRTUAL_BALANCE:.2f}$")
                        active_trades.remove(trade)
                    elif p_now <= trade['stop']:
                        VIRTUAL_BALANCE += (trade['cost'] * STOP_LOSS)
                        print(f"🛑 [خسارة] {trade['symbol']} | الرصيد: {VIRTUAL_BALANCE:.2f}$")
                        active_trades.remove(trade)

            time.sleep(40) # فحص متزن
        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            time.sleep(30)

if __name__ == "__main__":
    # 1. تشغيل خادم الويب في خلفية منفصلة
    t = Thread(target=run_web_server)
    t.start()
    
    # 2. تشغيل منطق التداول في الحلقية الرئيسية
    run_trading_logic()
