
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



exchange = ccxt.binance({'enableRateLimit': True})
active_positions = {}

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        response = requests.post(url, json=payload, timeout=10)
        # طباعة النتيجة في رندر للتأكد من وصول الرسالة كاملة
        print(f"Telegram Log: {response.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_duration(start_time):
    duration = datetime.now() - start_time
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m"

def monitor_positions():
    global active_positions
    for symbol, trade in list(active_positions.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            entry_price = trade['entry']
            
            # تأمين الصفقة عند ربح 2.5%
            if not trade['secured'] and current_price >= (entry_price * 1.025):
                trade['sl'] = entry_price
                trade['secured'] = True
                send_telegram_msg(f"🛡️ *تأمين:* `{symbol}`\nتم تحريك الوقف للدخول.")

            # الخروج بالهدف
            if current_price >= trade['tp']:
                dur = get_duration(trade['start_time'])
                msg = (f"🎯 *خروج: هدف محقق*\n"
                       f"💰 العملة: `{symbol}`\n"
                       f"📈 الربح: `+5.0%`\n"
                       f"⏱️ المدة: `{dur}`")
                send_telegram_msg(msg)
                del active_positions[symbol]

            # الخروج بالوقف
            elif current_price <= trade['sl']:
                dur = get_duration(trade['start_time'])
                res = "تعادل (تأمين)" if trade['secured'] else "ضرب الوقف"
                msg = (f"🛑 *خروج: {res}*\n"
                       f"💰 العملة: `{symbol}`\n"
                       f"⏱️ المدة: `{dur}`")
                send_telegram_msg(msg)
                del active_positions[symbol]
        except: continue

def check_new_signals():
    try:
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s]
        top_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]
        
        for symbol in top_symbols:
            if symbol in active_positions: continue
            
            bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # المؤشرات الفنية
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
            # حساب RSI مبسط
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['rsi'] = 100 - (100 / (1 + (gain / loss)))
            df['mid'] = df['close'].rolling(window=20).mean()
            
            last = df.iloc[-1]
            price = last['close']
            
            # شروط الاستراتيجية
            if price > last['ema200'] and 40 < last['rsi'] < 65 and price > last['mid']:
                entry = price
                tp = entry * 1.05
                sl = entry * 0.975 # وقف خسارة 2.5%
                
                active_positions[symbol] = {
                    'entry': entry,
                    'tp': tp,
                    'sl': sl,
                    'secured': False,
                    'start_time': datetime.now()
                }
                
                # الرسالة المعدلة لضمان ظهور وقف الخسارة
                msg = (f"🚀 *إشارة دخول جديدة*\n\n"
                       f"💎 *العملة:* `{symbol}`\n"
                       f"📥 *الدخول:* `{entry:.4f}`\n"
                       f"🎯 *الهدف:* `{tp:.4f}`\n"
                       f"🛑 *الوقف:* `{sl:.4f}`\n\n"
                       f"📊 *RSI:* `{last['rsi']:.1f}`")
                
                send_telegram_msg(msg)
    except: pass

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    send_telegram_msg("🔄 *تم التحديث:* نظام الإشارات جاهز الآن مع إظهار وقف الخسارة.")
    
    while True:
        check_new_signals()
        monitor_positions()
        time.sleep(60)


