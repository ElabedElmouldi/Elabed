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
FRIENDS_IDS = ["5067771509", "-1003692815602"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. إدارة الحالة ---
STATE_FILE = "bot_state.json"

def save_state(trades, balance, stats):
    state = {
        'trades': [],
        'current_balance': balance,
        'stats': stats,
        'last_report_date': stats.get('last_report_date', datetime.now().isoformat())
    }
    for t in trades:
        temp = t.copy()
        if isinstance(temp['open_time'], datetime): temp['open_time'] = temp['open_time'].isoformat()
        state['trades'].append(temp)
    with open(STATE_FILE, 'w') as f: json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                trades = data.get('trades', [])
                for t in trades: t['open_time'] = datetime.fromisoformat(t['open_time'])
                stats = data.get('stats', {'wins': 0, 'losses': 0, 'total_pnl': 0, 'last_report_date': datetime.now().isoformat()})
                return trades, data.get('current_balance', 500.0), stats
        except: pass
    return [], 500.0, {'wins': 0, 'losses': 0, 'total_pnl': 0, 'last_report_date': datetime.now().isoformat()}

# --- 3. خادم الويب ---
app = Flask('')
@app.route('/')
def home(): return f"🚀 Sniper v5.2 Mid-Cap | {datetime.now().strftime('%H:%M:%S')}"

# --- 4. الإعدادات الهجومية (قناص العملات المتوسطة) ---
MAX_TRADES = 5
PERCENT_PER_TRADE = 0.20
TRAILING_CALLBACK = 0.008
MIN_WIDTH = 0.045
# فلتر حجم التداول لاستبعاد العملات الصغيرة جداً والكبيرة جداً
MIN_VOL = 15000000    # 15 مليون دولار
MAX_VOL = 500000000   # 500 مليون دولار (استبعاد BTC, ETH, SOL...)

exchange = ccxt.binance({'enableRateLimit': True})
active_trades, CURRENT_TOTAL_BALANCE, stats = load_state()

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
        
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        return {'price': last['c'], 'lower': last['lower'], 'upper': last['upper'], 'rsi': rsi, 'width': width}
    except: return None

# --- 5. منطق التداول المطور ---
def run_trading_logic():
    global CURRENT_TOTAL_BALANCE, stats
    send_telegram("🏹 *تم تفعيل صائد العملات المتوسطة v5.2*\nالبحث: `200 عملة` | النطاق: `15M$ - 500M$`")

    while True:
        try:
            now = datetime.now()
            
            # أ. التقرير الدوري (كل 24 ساعة)
            last_report = datetime.fromisoformat(stats['last_report_date'])
            if now >= last_report + timedelta(days=1):
                win_rate = (stats['wins'] / (stats['wins'] + stats['losses']) * 100) if (stats['wins'] + stats['losses']) > 0 else 0
                send_telegram(f"📊 *تقرير 24 ساعة:*\nالرصيد: `{CURRENT_TOTAL_BALANCE:.2f}$` | النجاح: `{win_rate:.1f}%` | الربح الصافي: `{stats['total_pnl']:+.2f}$`")
                stats.update({'wins': 0, 'losses': 0, 'total_pnl': 0, 'last_report_date': now.isoformat()})
                save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)

            # ب. إدارة الصفقات المفتوحة
            if active_trades:
                tickers = exchange.fetch_tickers([t['symbol'] for t in active_trades])
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    if p_now > t['highest_price']: t['highest_price'] = p_now
                    if not t['break_even'] and p_now >= t['entry_price'] * 1.02:
                        t['stop'] = t['entry_price']
                        t['break_even'] = True
                    if p_now >= t['target_trigger']: t['trailing_active'] = True

                    close = (t['trailing_active'] and p_now <= t['highest_price'] * (1-TRAILING_CALLBACK)) or (p_now <= t['stop'])
                    
                    if close:
                        pnl = (p_now / t['entry_price']) - 1
                        profit_val = t['cost'] * pnl
                        CURRENT_TOTAL_BALANCE += profit_val
                        if profit_val > 0: stats['wins'] += 1
                        else: stats['losses'] += 1
                        stats['total_pnl'] += profit_val
                        active_trades.remove(t)
                        save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)
                        send_telegram(f"✅ *إغلاق:* `{t['symbol']}` | النتيجة: `{pnl*100:+.2f}%`")

            # ج. البحث الموسع (200 عملة متوسطة)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                # فلتر لاستبعاد العملات الثقيلة (BTC, ETH...) والعملات الميتة
                candidates = sorted([{'s': s, 'v': d['quoteVolume'], 'c': d['percentage']} 
                                    for s, d in all_tickers.items() 
                                    if '/USDT' in s and MIN_VOL < d['quoteVolume'] < MAX_VOL], 
                                    key=lambda x: abs(x['c']), reverse=True)[:200]
                
                for item in candidates:
                    symbol = item['s']
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    time.sleep(0.1) # سرعة فحص عالية جداً لمسح 200 عملة
                    data = get_analysis(symbol)
                    
                    if data and data['price'] <= data['lower'] and data['width'] >= MIN_WIDTH and data['rsi'] <= 35:
                        entry_amt = CURRENT_TOTAL_BALANCE * PERCENT_PER_TRADE
                        active_trades.append({
                            'symbol': symbol, 'entry_price': data['price'], 'cost': entry_amt,
                            'target_trigger': data['upper'], 'highest_price': data['price'],
                            'stop': data['price'] * 0.965, 'trailing_active': False, 
                            'break_even': False, 'open_time': now
                        })
                        save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)
                        send_telegram(f"🎯 *قنص ميد-كاب:* `{symbol}` | تذبذب: `{data['width']*100:.1f}%` | القيمة: `{entry_amt:.1f}$`")

            wait = 10 if any(t['trailing_active'] for t in active_trades) else 45
            time.sleep(wait)
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    run_trading_logic()
