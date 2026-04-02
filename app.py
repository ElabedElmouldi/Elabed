
import pandas as pd
import pandas_ta as ta
import requests
import time
import os

# --- بياناتك التي تعمل على VS Code ---
TOKEN = 8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68ا"
CHAT_ID = "5067771509"

active_trades = {} 

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}&parse_mode=Markdown"
        requests.get(url, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

exchange = ccxt.binance({'enableRateLimit': True})

def get_top_volume_symbols(limit=25):
    try:
        tickers = exchange.fetch_tickers()
        usdt_symbols = [s for s in tickers if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s]
        sorted_symbols = sorted(usdt_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        return sorted_symbols[:limit]
    except: return []

def monitor_active_trades():
    global active_trades
    for symbol, trade in list(active_trades.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            if not trade['is_secured'] and current_price >= (trade['entry'] * 1.025):
                trade['sl'] = trade['entry']
                trade['is_secured'] = True
                send_telegram_msg(f"🛡️ *تأمين:* `{symbol}` وصل لـ `+2.5%`.. الوقف عند الدخول.")
            if current_price >= trade['tp']:
                send_telegram_msg(f"🎯 *هدف محقق!* `{symbol}` ربح `+5.0%` 🔥")
                del active_trades[symbol]
            elif current_price <= trade['sl']:
                status = "تعادل" if trade['is_secured'] else "خسارة"
                send_telegram_msg(f"🛑 *خروج:* `{symbol}` ({status})")
                del active_trades[symbol]
        except: continue

def analyze_signal(symbol):
    global active_trades
    if symbol in active_trades: return 
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=210)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ema200'] = ta.ema(df['close'], length=200)
        df['ema21'] = ta.ema(df['close'], length=21)
        df['ema9'] = ta.ema(df['close'], length=9)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']
        
        is_bullish = current_price > last['ema200']
        crossover = (prev['ema9'] <= prev['ema21']) and (last['ema9'] > last['ema21'])
        vol_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_confirmed = last['volume'] > (vol_avg * 1.5)
        dist = ((current_price - last['ema21']) / last['ema21']) * 100

        if is_bullish and crossover and volume_confirmed and dist <= 2.5:
            entry = current_price
            active_trades[symbol] = {'entry': entry, 'tp': entry * 1.05, 'sl': max(last['ema21'], entry * 0.97), 'is_secured': False}
            send_telegram_msg(f"🚀 *إشارة:* `{symbol}`\nدخول: `{entry}`\nهدف: `{active_trades[symbol]['tp']}`\nمسافة: `{dist:.2f}%`")
    except: pass

print("⚙️ البوت يعمل بنظام الحاوية (Docker)...")
while True:
    try:
        symbols = get_top_volume_symbols(25)
        for sym in symbols:
            analyze_signal(sym)
            time.sleep(1)
        monitor_active_trades()
        time.sleep(60)
    except Exception as e:
        time.sleep(30)

import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import os

# --- إعدادات التلغرام (يفضل استخدام Environment Variables في رندر) ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID', 'YOUR_CHAT_ID')

active_trades = {} 

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}&parse_mode=Markdown"
        requests.get(url, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

exchange = ccxt.binance({'enableRateLimit': True})

def get_top_volume_symbols(limit=25):
    try:
        tickers = exchange.fetch_tickers()
        usdt_symbols = [s for s in tickers if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s]
        sorted_symbols = sorted(usdt_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        return sorted_symbols[:limit]
    except: return []

def monitor_active_trades():
    global active_trades
    for symbol, trade in list(active_trades.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            if not trade['is_secured'] and current_price >= (trade['entry'] * 1.025):
                trade['sl'] = trade['entry']
                trade['is_secured'] = True
                send_telegram_msg(f"🛡️ *تأمين:* `{symbol}` وصل لـ `+2.5%`.. الوقف عند الدخول.")
            if current_price >= trade['tp']:
                send_telegram_msg(f"🎯 *هدف محقق!* `{symbol}` ربح `+5.0%` 🔥")
                del active_trades[symbol]
            elif current_price <= trade['sl']:
                status = "تعادل" if trade['is_secured'] else "خسارة"
                send_telegram_msg(f"🛑 *خروج:* `{symbol}` ({status})")
                del active_trades[symbol]
        except: continue

def analyze_signal(symbol):
    global active_trades
    if symbol in active_trades: return 
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=210)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ema200'] = ta.ema(df['close'], length=200)
        df['ema21'] = ta.ema(df['close'], length=21)
        df['ema9'] = ta.ema(df['close'], length=9)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']
        
        is_bullish = current_price > last['ema200']
        crossover = (prev['ema9'] <= prev['ema21']) and (last['ema9'] > last['ema21'])
        vol_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_confirmed = last['volume'] > (vol_avg * 1.5)
        dist = ((current_price - last['ema21']) / last['ema21']) * 100

        if is_bullish and crossover and volume_confirmed and dist <= 2.5:
            entry = current_price
            active_trades[symbol] = {'entry': entry, 'tp': entry * 1.05, 'sl': max(last['ema21'], entry * 0.97), 'is_secured': False}
            send_telegram_msg(f"🚀 *إشارة:* `{symbol}`\nدخول: `{entry}`\nهدف: `{active_trades[symbol]['tp']}`\nمسافة: `{dist:.2f}%`")
    except: pass

print("⚙️ البوت يعمل بنظام الحاوية (Docker)...")
while True:
    try:
        symbols = get_top_volume_symbols(25)
        for sym in symbols:
            analyze_signal(sym)
            time.sleep(1)
        monitor_active_trades()
        time.sleep(60)
    except Exception as e:
        time.sleep(30)

