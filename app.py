"

# --- إعدادات التلغرام (يفضل استخدام Environment Variables في رندر) ---
import ccxt
import pandas as pd
import requests
import time
import os


# --- بياناتك التي تعمل على VS Code ---
TOKEN = 8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68ا"
CHAT_ID = "5067771509
# --- إعدادات التلغرام ---


active_trades = {} 

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}&parse_mode=Markdown"
        requests.get(url, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

# دالة حساب EMA يدوياً بدون مكتبات إضافية
def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

exchange = ccxt.binance({'enableRateLimit': True})

def get_top_volume_symbols(limit=20):
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
            
            # تأمين عند 2.5%
            if not trade['is_secured'] and current_price >= (trade['entry'] * 1.025):
                trade['sl'] = trade['entry']
                trade['is_secured'] = True
                send_telegram_msg(f"🛡️ *تأمين صفقة:* `{symbol}`\nوصل الربح لـ `+2.5%`.. الوقف عند الدخول.")

            # هدف 5%
            if current_price >= trade['tp']:
                send_telegram_msg(f"🎯 *هدف محقق!* `{symbol}`\nربح صافي `+5.0%` 🔥")
                del active_trades[symbol]
            
            # وقف خسارة
            elif current_price <= trade['sl']:
                status = "خروج تعادل" if trade['is_secured'] else "ضرب الوقف"
                send_telegram_msg(f"🛑 *إغلاق صفقة:* `{symbol}`\nالنتيجة: `{status}`")
                del active_trades[symbol]
        except: continue

def analyze_signal(symbol):
    global active_trades
    if symbol in active_trades: return 
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=210)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # حساب المؤشرات يدوياً باستخدام Pandas فقط
        df['ema200'] = calculate_ema(df['close'], 200)
        df['ema21'] = calculate_ema(df['close'], 21)
        df['ema9'] = calculate_ema(df['close'], 9)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']
        
        # الشروط الفنية
        is_bullish = current_price > last['ema200']
        crossover = (prev['ema9'] <= prev['ema21']) and (last['ema9'] > last['ema21'])
        vol_avg = df['volume'].rolling(window=20).mean().iloc[-1]
        volume_confirmed = last['volume'] > (vol_avg * 1.5)
        dist = ((current_price - last['ema21']) / last['ema21']) * 100

        if is_bullish and crossover and volume_confirmed and dist <= 2.5:
            entry = current_price
            active_trades[symbol] = {
                'entry': entry, 
                'tp': entry * 1.05, 
                'sl': max(last['ema21'], entry * 0.97), 
                'is_secured': False
            }
            send_telegram_msg(f"🚀 *إشارة دخول:* `{symbol}`\nدخول: `{entry}`\nالهدف: `{active_trades[symbol]['tp']}`")
    except: pass

# --- رسالة تأكيد التشغيل عند البداية ---
send_telegram_msg("✅ *تم تشغيل البوت بنجاح!*\nالبوت يراقب الآن أفضل 20 عملة سيولة على بينانس بنظام التأمين التلقائي.")

print("⚙️ البوت يعمل الآن (بدور مكتبة pandas-ta)...")
while True:
    try:
        symbols = get_top_volume_symbols(20)
        for sym in symbols:
            analyze_signal(sym)
            time.sleep(1)
        monitor_active_trades()
        time.sleep(60)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(30)
