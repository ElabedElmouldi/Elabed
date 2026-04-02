

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
# قائمة المعرفات: ايدي القناة (يبدأ بـ -100) وايدي حسابك الشخصي
RECIPIENTS = ['-1003692815602', '5067771509'] 
# ==========================================================

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

exchange = ccxt.binance()
DATA_FILE = 'trades_v2.json'

def load_trades():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return json.load(f)
        except: pass
    return []

def save_trades(trades):
    with open(DATA_FILE, 'w') as f: json.dump(trades, f, indent=4)

def send_telegram(text):
    """إرسال الرسالة لكل من القناة والبوت الشخصي"""
    for chat_id in RECIPIENTS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, data=payload)
            res_data = response.json()
            if not res_data.get("ok"):
                print(f"❌ فشل الإرسال للمعرف {chat_id}: {res_data.get('description')}")
        except Exception as e:
            print(f"❌ خطأ في الإرسال: {e}")

def calculate_indicators(df):
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

def main():
    # 1. رسالة ترحيب عند التشغيل
    send_telegram("🚀 *تم تشغيل البوت بنجاح!*\nسيتم إرسال التنبيهات هنا وفي القناة.")
    
    while True:
        try:
            # 2. رسالة "دراسة السوق" تظهر في الـ Logs فقط لتقليل الإزعاج
            # إذا أردتها في تلغرام، قم بإلغاء التعليق عن السطر التالي:
            # send_telegram("🔍 جاري فحص السوق الآن...")
            print(f"🔍 فحص السوق: {datetime.now().strftime('%H:%M:%S')}")

            trades = load_trades()
            updated_trades = []
            
            # تحديث الصفقات المفتوحة
            for trade in trades:
                curr_p = exchange.fetch_ticker(trade['symbol'])['last']
                diff = ((curr_p - trade['entry_price']) / trade['entry_price']) * 100
                
                # تأمين عند 3%
                if diff >= 3.0 and not trade.get('is_secured', False):
                    trade['stop_loss'] = trade['entry_price']
                    trade['is_secured'] = True
                    send_telegram(f"🛡️ *تأمين صفقة:* `{trade['symbol']}`\nالربح وصل 3%، تم نقل الوقف لنقطة الدخول.")

                # هدف 6%
                if curr_p >= trade['take_profit']:
                    send_telegram(f"✅ *الهدف تحقق (6%)*\nالعملة: `{trade['symbol']}`\nالنتيجة: ربح صافي")
                    continue

                # وقف -3%
                elif curr_p <= trade['stop_loss']:
                    status = "🛡️ خروج متعادل" if trade.get('is_secured') else "❌ ضرب الوقف (-3%)"
                    send_telegram(f"🏁 *إغلاق صفقة:* `{trade['symbol']}`\nالنتيجة: {status}")
                    continue
                
                updated_trades.append(trade)
            
            save_trades(updated_trades)

            # فحص فرص جديدة
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
                    tp = entry_p * 1.06
                    sl = entry_p * 0.97
                    
                    new_trade = {
                        "symbol": sym, "entry_price": entry_p,
                        "take_profit": tp, "stop_loss": sl, "is_secured": False
                    }
                    updated_trades.append(new_trade)
                    save_trades(updated_trades)
                    
                    send_telegram(f"📥 *دخول صفقة:* `{sym}`\n💵 السعر: `{entry_p}`\n🎯 الهدف: `{tp:.4f}`\n🛑 الوقف: `{sl:.4f}`")

        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            
        time.sleep(600) # فحص كل 10 دقائق

if __name__ == "__main__":
    main()

