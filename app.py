
import ccxt
import pandas as pd
import requests
import time
import os
import threading
import http.server
import socketserver



# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "5067771509"



exchange = ccxt.binance({'enableRateLimit': True})

# دالة إرسال الرسائل
def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=10)
    except: pass

# دالة حساب المؤشرات الفنية (EMA) يدوياً باستخدام Pandas
def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

# دالة فحص العملات القوية (أعلى سيولة)
def get_signals():
    try:
        tickers = exchange.fetch_tickers()
        # تصفية العملات المقابلة لـ USDT فقط واستبعاد العملات الرافعة (UP/DOWN)
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s]
        # ترتيب حسب حجم التداول واختيار أفضل 15 عملة
        top_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]
        
        for symbol in top_symbols:
            bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # حساب المتوسطات
            df['ema200'] = calculate_ema(df['close'], 200)
            df['ema21'] = calculate_ema(df['close'], 21)
            df['ema9'] = calculate_ema(df['close'], 9)
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # شروط الاستراتيجية (تقاطع + اتجاه صاعد)
            is_bullish = last['close'] > last['ema200']
            crossover = (prev['ema9'] <= prev['ema21']) and (last['ema9'] > last['ema21'])
            
            if is_bullish and crossover:
                entry = last['close']
                tp = entry * 1.05  # هدف 5%
                sl = entry * 0.97  # وقف 3%
                
                msg = f"🚀 *إشارة دخول جديدة!*\nالعملة: `{symbol}`\nالدخول: `{entry}`\nالهدف (5%): `{tp:.4f}`\nالوقف: `{sl:.4f}`"
                send_telegram_msg(msg)
                print(f"Signal found for {symbol}")
                
    except Exception as e:
        print(f"Error in analysis: {e}")

# --- خادم وهمي لإرضاء Render ---
def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    
    send_telegram_msg("✅ *تحديث:* تم تفعيل استراتيجية التداول (EMA + 5%). البوت يراقب السوق الآن...")
    
    while True:
        get_signals()
        time.sleep(3600) # فحص كل ساعة (لأن الفريم المستخدم هو ساعة)


