import ccxt
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. إدارة الذاكرة والتراكم ---
TRADES_FILE = "active_trades.json"
BALANCE_FILE = "account_balance.json"

def save_state(trades, balance):
    state = {
        'trades': [],
        'current_balance': balance
    }
    for t in trades:
        temp = t.copy()
        if isinstance(temp['open_time'], datetime): temp['open_time'] = temp['open_time'].isoformat()
        state['trades'].append(temp)
    with open(TRADES_FILE, 'w') as f: json.dump(state, f)

def load_state():
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r') as f:
                data = json.load(f)
                trades = data.get('trades', [])
                for t in trades: t['open_time'] = datetime.fromisoformat(t['open_time'])
                return trades, data.get('current_balance', 500.0)
        except: return [], 500.0
    return [], 500.0

# --- 3. خادم الويب ---
app = Flask('')
@app.route('/')
def home(): return f"🚀 Aggressive Sniper v5.0 | {datetime.now().strftime('%H:%M:%S')}"

# --- 4. الإعدادات الهجومية ---
MAX_TRADES = 5
PERCENT_PER_TRADE = 0.20  # 20% من الرصيد الحالي لكل صفقة
TRAILING_CALLBACK = 0.01  # تراجع 1% من القمة
MIN_VOL_24H = 15000000    # رفع السيولة لـ 15 مليون لضمان السرعة
MIN_WIDTH = 0.04          # رفع عرض القناة لـ 4% لاستهداف أرباح أكبر

exchange = ccxt.binance({'enableRateLimit': True})
active_trades, CURRENT_TOTAL_BALANCE = load_state()

# --- 5. وظائف التحليل الذكي ---
def get_analysis(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['ma20'] = df['c'].rolling(20).mean()
        df['std'] = df['c'].rolling(20).std()
        df['lower'] = df['ma20'] - (df['std'] * 2)
        df['upper'] = df['ma20'] + (df['std'] * 2)
        
        last = df.iloc[-1]
        width = (last['upper'] - last['lower']) / last['ma20']
        
        # حساب RSI للتشبع
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        return {'price': last['c'], 'lower': last['lower'], 'upper': last['upper'], 'rsi': rsi, 'width': width}
    except: return None

# --- 6. المنطق الرئيسي (الهجومي) ---
def run_trading_logic():
    global CURRENT_TOTAL_BALANCE
    send_telegram("🚀 *تم إطلاق النسخة الهجومية 5.0*\nالهدف: `5% يومياً`\nالنظام: `تراكمي + تتبع فائق`")

    while True:
        try:
            now = datetime.now()
            
            # أ. إدارة وتتبع الأرباح
            if active_trades:
                tickers = exchange.fetch_tickers([t['symbol'] for t in active_trades])
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    if p_now > t['highest_price']: t['highest_price'] = p_now
                    
                    # تأمين الصفقة: إذا ربحنا 2%، ارفع الوقف لنقطة الدخول
                    if not t['break_even'] and p_now >= t['entry_price'] * 1.02:
                        t['stop'] = t['entry_price']
                        t['break_even'] = True
                        send_telegram(f"🛡️ *تأمين:* `{t['symbol']}` تم رفع الوقف لنقطة الدخول.")

                    if p_now >= t['target_trigger']: t['trailing_active'] = True

                    # قرار الإغلاق
                    close = (t['trailing_active'] and p_now <= t['highest_price'] * (1-TRAILING_CALLBACK)) or (p_now <= t['stop'])
                    
                    if close:
                        pnl = (p_now / t['entry_price']) - 1
                        profit_val = t['cost'] * pnl
                        CURRENT_TOTAL_BALANCE += profit_val # تحديث الرصيد التراكمي
                        
                        active_trades.remove(t)
                        save_state(active_trades, CURRENT_TOTAL_BALANCE)
                        
                        status = "💰" if profit_val > 0 else "🛑"
                        send_telegram(f"{status} *إغلاق:* `{t['symbol']}`\nربح: `{pnl*100:+.2f}%` | رصيد جديد: `{CURRENT_TOTAL_BALANCE:.2f}$`")

            # ب. البحث المكثف عن فرص
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                # فلترة وترتيب حسب "قوة الانفجار" (أعلى نسبة تغير)
                candidates = sorted([{'s': s, 'v': d['quoteVolume'], 'c': d['percentage']} 
                                    for s, d in all_tickers.items() 
                                    if '/USDT' in s and d['quoteVolume'] > MIN_VOL_24H], 
                                    key=lambda x: abs(x['c']), reverse=True)[:40]
                
                for item in candidates:
                    symbol = item['s']
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    time.sleep(0.2) # سرعة فحص أعلى
                    data = get_analysis(symbol)
                    
                    if data and data['price'] <= data['lower'] and data['width'] >= MIN_WIDTH and data['rsi'] <= 40:
                        # حساب حجم الصفقة بناءً على الرصيد الحالي (تراكمي)
                        entry_amt = CURRENT_TOTAL_BALANCE * PERCENT_PER_TRADE
                        
                        active_trades.append({
                            'symbol': symbol, 'entry_price': data['price'], 'cost': entry_amt,
                            'target_trigger': data['upper'], 'highest_price': data['price'],
                            'stop': data['price'] * 0.96, 'trailing_active': False, 
                            'break_even': False, 'open_time': now
                        })
                        save_state(active_trades, CURRENT_TOTAL_BALANCE)
                        send_telegram(f"🎯 *قنص فرصة:* `{symbol}`\nتذبذب: `{data['width']*100:.1f}%` | القيمة: `{entry_amt:.1f}$`")

            wait = 10 if any(t['trailing_active'] for t in active_trades) else 45
            time.sleep(wait)
        except: time.sleep(20)

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    run_trading_logic()
