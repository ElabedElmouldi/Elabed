import ccxt
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام (تأكد من وضع بياناتك هنا) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. إدارة الحالة والذاكرة ---
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

# --- 3. خادم الويب (Render Keep-Alive) ---
app = Flask('')
@app.route('/')
def home(): return f"🚀 Sniper v5.3 Full Detail | {datetime.now().strftime('%H:%M:%S')}"

# --- 4. الإعدادات الهجومية (Mid-Cap Sniper) ---
MAX_TRADES = 5
PERCENT_PER_TRADE = 0.20
TRAILING_CALLBACK = 0.008 
MIN_WIDTH = 0.045
MIN_VOL = 15000000    # 15 مليون دولار
MAX_VOL = 500000000   # 500 مليون دولار (استبعاد العملات الضخمة)

exchange = ccxt.binance({'enableRateLimit': True})
active_trades, CURRENT_TOTAL_BALANCE, stats = load_state()

# --- 5. وظائف التحليل الفني ---
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

# --- 6. حلقة التداول الرئيسية ---
def run_trading_logic():
    global CURRENT_TOTAL_BALANCE, stats
    send_telegram("🦾 *تم تشغيل القناص v5.3 الاحترافي*\nنطاق البحث: `200 عملة متوسطة`\nالهدف: `5% يومياً تراكمي`")

    while True:
        try:
            now = datetime.now()
            
            # أ. نظام التقارير اليومية (كل 24 ساعة)
            last_report_dt = datetime.fromisoformat(stats['last_report_date'])
            if now >= last_report_dt + timedelta(days=1):
                win_rate = (stats['wins'] / (stats['wins'] + stats['losses']) * 100) if (stats['wins'] + stats['losses']) > 0 else 0
                report_msg = (f"📊 *تقرير الأداء (24 ساعة)*\n\n"
                              f"💰 الرصيد الحالي: `{CURRENT_TOTAL_BALANCE:.2f}$`\n"
                              f"✅ صفقات ناجحة: `{stats['wins']}`\n"
                              f"❌ صفقات خاسرة: `{stats['losses']}`\n"
                              f"📈 نسبة النجاح: `{win_rate:.1f}%`\n"
                              f"💵 ربح اليوم الصافي: `{stats['total_pnl']:+.2f}$`\n"
                              f"🚀 الحالة: `في تقدم نحو الهدف`")
                send_telegram(report_msg)
                stats.update({'wins': 0, 'losses': 0, 'total_pnl': 0, 'last_report_date': now.isoformat()})
                save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)

            # ب. مراقبة وإدارة الصفقات المفتوحة
            if active_trades:
                tickers = exchange.fetch_tickers([t['symbol'] for t in active_trades])
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    if p_now > t['highest_price']: t['highest_price'] = p_now
                    
                    # تأمين الصفقة عند ربح 2%
                    if not t['break_even'] and p_now >= t['entry_price'] * 1.02:
                        t['stop'] = t['entry_price']
                        t['break_even'] = True
                        send_telegram(f"🛡️ *تأمين:* `{t['symbol']}` (رفع الوقف لنقطة الدخول)")

                    if p_now >= t['target_trigger']: t['trailing_active'] = True

                    # قرار الإغلاق (تتبع أو وقف خسارة)
                    close_cond = (t['trailing_active'] and p_now <= t['highest_price'] * (1-TRAILING_CALLBACK)) or (p_now <= t['stop'])
                    
                    if close_cond:
                        pnl = (p_now / t['entry_price']) - 1
                        profit_val = t['cost'] * pnl
                        CURRENT_TOTAL_BALANCE += profit_val
                        
                        if profit_val > 0: stats['wins'] += 1
                        else: stats['losses'] += 1
                        stats['total_pnl'] += profit_val
                        
                        active_trades.remove(t)
                        save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)
                        
                        icon = "✅" if profit_val > 0 else "🛑"
                        send_telegram(f"{icon} *إغلاق صفقة:* `{t['symbol']}`\nالربح: `{pnl*100:+.2f}%`\nالرصيد: `{CURRENT_TOTAL_BALANCE:.2f}$`")

            # ج. البحث عن فرص (200 عملة)
            if len(active_trades) < MAX_TRADES:
                all_tickers = exchange.fetch_tickers()
                # فلترة العملات (السيولة بين 15M و 500M) والترتيب حسب القوة
                candidates = sorted([{'s': s, 'v': d['quoteVolume'], 'c': d['percentage']} 
                                    for s, d in all_tickers.items() 
                                    if '/USDT' in s and MIN_VOL < d['quoteVolume'] < MAX_VOL], 
                                    key=lambda x: abs(x['c']), reverse=True)[:200]
                
                for item in candidates:
                    symbol = item['s']
                    if symbol in [t['symbol'] for t in active_trades]: continue
                    if len(active_trades) >= MAX_TRADES: break
                    
                    time.sleep(0.1) # سرعة فحص عالية
                    data = get_analysis(symbol)
                    
                    if data and data['price'] <= data['lower'] and data['width'] >= MIN_WIDTH and data['rsi'] <= 35:
                        entry_amt = CURRENT_TOTAL_BALANCE * PERCENT_PER_TRADE
                        sl_price = data['price'] * 0.965  # وقف 3.5%
                        tp_trigger = data['upper']      # الهدف المبدئي
                        
                        active_trades.append({
                            'symbol': symbol, 'entry_price': data['price'], 'cost': entry_amt,
                            'target_trigger': tp_trigger, 'highest_price': data['price'],
                            'stop': sl_price, 'trailing_active': False, 
                            'break_even': False, 'open_time': now
                        })
                        save_state(active_trades, CURRENT_TOTAL_BALANCE, stats)
                        
                        # إشعار الدخول التفصيلي
                        entry_msg = (f"🎯 *فتح صفقة جديدة*\n\n"
                                     f"💎 العملة: `{symbol}`\n"
                                     f"💰 سعر الدخول: `{data['price']:.4f}`\n"
                                     f"💵 قيمة الصفقة: `{entry_amt:.1f}$`\n"
                                     f"🛑 وقف الخسارة: `{sl_price:.4f}`\n"
                                     f"🎯 جني الأرباح (مبدئي): `{tp_trigger:.4f}`\n\n"
                                     f"📊 تذبذب القناة: `{data['width']*100:.1f}%`")
                        send_telegram(entry_msg)

            # د. توقيت الفحص
            wait = 10 if any(t['trailing_active'] for t in active_trades) else 45
            time.sleep(wait)
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    # تشغيل الخادم والمنطق
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    run_trading_logic()
