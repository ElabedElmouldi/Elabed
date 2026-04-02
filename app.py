

import ccxt
import pandas as pd
import requests
import time
import json
import os
import threading
from flask import Flask
from datetime import datetime

# ================= إعدادات التلغرام الخاصة بك =================
TELEGRAM_TOKEN = '8ف439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68'
USER_ID = '5067771509'
# ==========================================================

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Online - BB + RSI + SMA200 + EMA(9/21) + Volume", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

exchange = ccxt.binance()
DATA_FILE = 'trades_data.json'

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
    payload = {"chat_id": USER_ID, "text": text, "parse_mode": "Markdown"}
    try: requests.post(url, data=payload)
    except: print("Telegram Error")

def calculate_indicators(df):
    # 1. Bollinger Bands (20, 2)
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    
    # 2. RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    # 3. SMA 200 (الاتجاه العام)
    df['sma200'] = df['close'].rolling(window=200).mean()
    
    # 4. EMA 9 & EMA 21 (الزخم)
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    
    # 5. Volume MA (متوسط الفوليوم لـ 20 شمعة)
    df['vol_ma'] = df['vol'].rolling(window=20).mean()
    
    return df

def main():
    send_telegram(f"🚀 *تم تحديث البوت بإضافة شرط الفوليوم!*\n"
                   f"📊 الشروط: BB + RSI + SMA200 + EMA(9/21) + High Volume\n"
                   f"⏱️ الفحص الدوري: كل 15 دقيقة")

    while True:
        try:
            send_telegram("🔍 *فحص السوق (بحث عن اختراق حقيقي بالفوليوم)...*")
            trades = load_trades()
            updated_trades = []
            
            # مراقبة الصفقات المفتوحة
            for trade in trades:
                ticker = exchange.fetch_ticker(trade['symbol'])
                curr_p = ticker['last']
                diff = ((curr_p - trade['entry_price']) / trade['entry_price']) * 100
                
                if diff >= 3.0 and not trade.get('is_secured', False):
                    trade['stop_loss'] = trade['entry_price']
                    trade['is_secured'] = True
                    send_telegram(f"🛡️ *تأمين:* `{trade['symbol']}`\nالربح 3%، الوقف عند الدخول.")

                if curr_p >= trade['take_profit']:
                    send_telegram(f"✅ *الهدف (6%):* `{trade['symbol']}`")
                    continue

                elif curr_p <= trade['stop_loss']:
                    res = "🛡️ خروج متعادل" if trade.get('is_secured') else "❌ ضرب الوقف"
                    send_telegram(f"🔚 *إغلاق:* `{trade['symbol']}`\nالنتيجة: {res}")
                    continue
                
                updated_trades.append(trade)
            
            save_trades(updated_trades)

            # فحص فرص جديدة
            tickers = exchange.fetch_tickers()
            symbols = [s for s in tickers if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
            top_50 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

            for sym in top_50:
                if any(t['symbol'] == sym for t in updated_trades): continue
                
                bars = exchange.fetch_ohlcv(sym, timeframe='1h', limit=250)
                df = calculate_indicators(pd.DataFrame(bars, columns=['ts','o','h','l','c','v']))
                last = df.iloc[-1]
                prev = df.iloc[-2]

                # --- شروط الدخول الاحترافية ---
                cond_trend = last['c'] > last['sma200']        # السعر فوق المتوسط 200
                cond_ema = last['ema9'] > last['ema21']         # 9 فوق 21
                cond_bb = last['c'] > last['upper'] and prev['c'] <= prev['upper']  # اختراق البولينجر
                cond_rsi = last['rsi'] > 60                    # قوة شرائية
                cond_vol = last['vol'] > (last['vol_ma'] * 1.2) # الفوليوم أعلى من المتوسط بـ 20%

                if cond_trend and cond_ema and cond_bb and cond_rsi and cond_vol:
                    
                    entry_p = last['c']
                    tp = entry_p * 1.06
                    sl = entry_p * 0.97
                    
                    new_trade = {
                        "symbol": sym, "entry_price": entry_p,
                        "take_profit": tp, "stop_loss": sl, "is_secured": False
                    }
                    updated_trades.append(new_trade)
                    save_trades(updated_trades)
                    
                    send_telegram(f"📥 *صفقة مثالية (اختراق مدعوم بالفوليوم):*\n"
                                   f"🪙 العملة: `{sym}`\n"
                                   f"📊 الفوليوم: `{last['vol']:.0f}` (أعلى من المتوسط)\n"
                                   f"💵 الدخول: `{entry_p}`\n"
                                   f"🎯 الهدف: `{tp:.4f}`\n"
                                   f"🛑 الوقف: `{sl:.4f}`")

        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(900) # 15 دقيقة

if __name__ == "__main__":
    main()
