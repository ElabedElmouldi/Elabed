
import ccxt
import pandas as pd
import requests
import time
import os
import threading
import http.server
import socketserver
from datetime import datetime

# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "5067771509"


exchange = ccxt.binance({'enableRateLimit': True})
active_positions = {}

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=10)
    except: pass

# دالة لحساب مدة الصفقة بشكل مقروء
def get_duration(start_time):
    duration = datetime.now() - start_time
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(hours)} ساعة و {int(minutes)} دقيقة"

# --- نظام مراقبة الصفقات المطور ---
def monitor_positions():
    global active_positions
    for symbol, trade in list(active_positions.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            entry_price = trade['entry']
            
            # 1. تأمين الصفقة عند ربح 2.5%
            if not trade['secured'] and current_price >= (entry_price * 1.025):
                trade['sl'] = entry_price
                trade['secured'] = True
                send_telegram_msg(f"🛡️ *تأمين صفقة:* `{symbol}`\nوصل الربح لـ `+2.5%`.. تم نقل الوقف للدخول.")

            # 2. الخروج عند الهدف (5%)
            if current_price >= trade['tp']:
                duration_str = get_duration(trade['start_time'])
                profit_percent = ((current_price - entry_price) / entry_price) * 100
                msg = (f"🎯 *نتيجة خروج: هدف محقق*\n"
                       f"---------------------------\n"
                       f"💰 العملة: `{symbol}`\n"
                       f"📈 الربح المحقق: `+{profit_percent:.2f}%` 🔥\n"
                       f"⏱️ مدة الصفقة: `{duration_str}`\n"
                       f"---------------------------")
                send_telegram_msg(msg)
                del active_positions[symbol]

            # 3. الخروج عند الوقف (تأمين أو خسارة)
            elif current_price <= trade['sl']:
                duration_str = get_duration(trade['start_time'])
                result_type = "خروج تعادل (تأمين)" if trade['secured'] else "ضرب وقف الخسارة"
                loss_percent = ((current_price - entry_price) / entry_price) * 100
                
                msg = (f"🛑 *نتيجة خروج: {result_type}*\n"
                       f"---------------------------\n"
                       f"💰 العملة: `{symbol}`\n"
                       f"📉 النتيجة: `{loss_percent:.2f}%`\n"
                       f"⏱️ مدة الصفقة: `{duration_str}`\n"
                       f"---------------------------")
                send_telegram_msg(msg)
                del active_positions[symbol]
                
        except Exception as e:
            print(f"Error monitoring {symbol}: {e}")

# --- نظام فحص الإشارات ---
def check_new_signals():
    try:
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s]
        top_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]
        
        for symbol in top_symbols:
            if symbol in active_positions: continue
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # حساب المؤشرات
            close = df['close']
            df['ema200'] = close.ewm(span=200, adjust=False).mean()
            # RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['rsi'] = 100 - (100 / (1 + (gain / loss)))
            # Bollinger Bands
            sma = close.rolling(window=20).mean()
            df['mid'] = sma
            
            last = df.iloc[-1]
            price = last['close']
            
            if price > last['ema200'] and 40 < last['rsi'] < 65 and price > last['mid']:
                active_positions[symbol] = {
                    'entry': price,
                    'tp': price * 1.05,
                    'sl': price * 0.975, # وقف 2.5%
                    'secured': False,
                    'start_time': datetime.now() # تسجيل وقت الدخول
                }
                send_telegram_msg(f"🚀 *دخول صفقة:* `{symbol}`\nالسعر: `{price}`\nالهدف: `{active_positions[symbol]['tp']:.4f}`")
    except Exception as e:
        print(f"Analysis Error: {e}")

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    send_telegram_msg("✅ *تحديث النظام:*\nتم تفعيل حساب مدة الصفقات وتحليل نتائج الخروج.")
    
    while True:
        check_new_signals()
        monitor_positions()
        time.sleep(60)


