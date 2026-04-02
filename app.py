import ccxt
import pandas as pd
import requests
import time
import json
import os
import threading
from flask import Flask
from datetime import datetime

# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8ف439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "-1003692815602"



app = Flask(__name__)
@app.route('/')
def home(): return "Trading Bot is Active", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

exchange = ccxt.binance()
DATA_FILE = 'active_trades_v2.json'

def load_trades():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return []

def save_trades(trades):
    with open(DATA_FILE, 'w') as f: json.dump(trades, f, indent=4)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except: print("Telegram Error")

def calculate_indicators(df):
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

def main():
    send_telegram("🚀 *تم تشغيل البوت بنجاح!*\n*الإعدادات:* هدف 6% | وقف 3% | تأمين عند 3%")
    
    while True:
        try:
            trades = load_trades()
            
            # 1. مراقبة وتحديث الصفقات المفتوحة
            updated_trades = []
            for trade in trades:
                curr_p = exchange.fetch_ticker(trade['symbol'])['last']
                diff = ((curr_p - trade['entry_price']) / trade['entry_price']) * 100
                
                # أ- تأمين الصفقة عند ربح 3%
                if diff >= 3.0 and not trade.get('is_secured', False):
                    trade['stop_loss'] = trade['entry_price']
                    trade['is_secured'] = True
                    send_telegram(f"🛡️ *تم تأمين الصفقة:* `{trade['symbol']}`\nتم تحريك وقف الخسارة إلى نقطة الدخول `{trade['entry_price']}` بعد ارتفاع السعر بـ 3%.")

                # ب- تحقق الهدف (6%)
                if curr_p >= trade['take_profit']:
                    send_telegram(f"💰 *نتيجة الصفقة: نصر (Target Hit)*\nالعملة: `{trade['symbol']}`\nسعر الخروج: `{curr_p}`\nالربح: `+6%` ✅")
                    continue # حذف من القائمة

                # ج- تحقق وقف الخسارة
                elif curr_p <= trade['stop_loss']:
                    res_text = "🛡️ خروج بنقطة الدخول (تأمين)" if trade.get('is_secured') else "🛑 خسارة -3%"
                    send_telegram(f"🏁 *نتيجة الصفقة: إغلاق*\nالعملة: `{trade['symbol']}`\nسعر الخروج: `{curr_p}`\nالنتيجة: `{res_text}`")
                    continue # حذف من القائمة
                
                updated_trades.append(trade)
            
            save_trades(updated_trades)

            # 2. البحث عن فرص جديدة
            tickers = exchange.fetch_tickers()
            symbols = [s for s in tickers if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
            top_50 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

            for sym in top_50:
                if any(t['symbol'] == sym for t in updated_trades): continue
                
                bars = exchange.fetch_ohlcv(sym, timeframe='1h', limit=50)
                df = calculate_indicators(pd.DataFrame(bars, columns=['ts','o','h','l','c','v']))
                last = df.iloc[-1]
                prev = df.iloc[-2]

                if last['c'] > last['upper'] and prev['c'] <= prev['upper'] and last['rsi'] > 60:
                    entry_p = last['c']
                    tp = entry_p * 1.06 # هدف 6%
                    sl = entry_p * 0.97 # وقف 3%
                    
                    new_trade = {
                        "symbol": sym,
                        "entry_price": entry_p,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "is_secured": False
                    }
                    updated_trades.append(new_trade)
                    save_trades(updated_trades)
                    
                    msg = (f"📥 *دخول صفقة جديدة:*\n"
                           f"📊 العملة: `{sym}`\n"
                           f"💵 الدخول: `{entry_p}`\n"
                           f"🎯 الهدف: `{tp:.4f}` (6%)\n"
                           f"🛑 الوقف: `{sl:.4f}` (-3%)")
                    send_telegram(msg)

        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(600)

if __name__ == "__main__":
    main()
