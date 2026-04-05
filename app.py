import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os
import requests

# --- 1. إعدادات التلجرام (التوكن والقائمة) ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram_to_all(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"⚠️ خطأ إرسال لـ {chat_id}: {e}")

# --- 2. خادم الويب (Keep-Alive) لمنع خمول Render ---
app = Flask('')
@app.route('/')
def home(): return f"🚀 Bot is running... {datetime.now().strftime('%H:%M:%S')}"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 3. إعدادات استراتيجية التداول ---
exchange = ccxt.binance({'enableRateLimit': True})
VIRTUAL_BALANCE = 100.0   
PERCENT_PER_TRADE = 0.20 
MAX_TRADES = 5           
TARGET_PROFIT = 1.04     
STOP_LOSS = 0.98         
MIN_VOLUME = 10000000    

active_trades = []
daily_closed_trades = []

# --- 4. وظائف جلب البيانات والتحليل ---

def get_top_gainers():
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        exclude = ['BTC/USDT', 'ETH/USDT', 'USDC/USDT', 'FDUSD/USDT', 'DAI/USDT']
        for s, d in tickers.items():
            if '/USDT' in s and s not in exclude and d['quoteVolume'] > MIN_VOLUME:
                gainers.append({'symbol': s, 'percentage': d['percentage']})
        gainers.sort(key=lambda x: x['percentage'], reverse=True)
        return [item['symbol'] for item in gainers[:100]]
    except: return []

def get_indicators(symbol):
    try:
        time.sleep(0.1)
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        df['ma'] = df['c'].rolling(window=20).mean()
        return df.iloc[-1]
    except: return None

# --- 5. أنظمة التقارير المحدثة ---

def send_open_trades_report():
    """تقرير الساعتين: جدول الصفقات المفتوحة مع أعلى وأقل نسبة"""
    if not active_trades:
        send_telegram_to_all("🔍 *تقرير الساعتين:* \nلا توجد صفقات مفتوحة حالياً.")
        return
    
    report = "📋 *تقرير المتابعة (كل 2س)* \n"
    report += "`العملة | دخول | وقت | أعلى% | أقل%` \n"
    report += "`---------------------------------` \n"
    
    for t in active_trades:
        try:
            # جلب حركة السعر منذ الدخول لحساب القمة والقاع
            since = int(t['open_time'].timestamp() * 1000)
            bars = exchange.fetch_ohlcv(t['symbol'], timeframe='1m', since=since)
            df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            high_p = ((df['h'].max() - t['entry_price']) / t['entry_price']) * 100
            low_p = ((df['l'].min() - t['entry_price']) / t['entry_price']) * 100
            
            sym = t['symbol'].split('/')[0][:5]
            report += f"`{sym:<5} | {t['entry_price']:.2f} | {t['open_time'].strftime('%H:%M')} | {high_p:+.1f}% | {low_p:+.1f}%` \n"
        except:
            report += f"`{t['symbol'][:5]:<5} | {t['entry_price']:.2f} | {t['open_time'].strftime('%H:%M')} | -- | --` \n"
    
    report += "`---------------------------------` \n"
    send_telegram_to_all(report)

def send_daily_summary():
    """التقرير اليومي الختامي بجدول وإحصائيات كاملة"""
    global daily_closed_trades
    if not daily_closed_trades:
        send_telegram_to_all("📊 *التقرير اليومي:* لا صفقات مغلقة اليوم.")
        return
    
    total = len(daily_closed_trades)
    wins = len([t for t in daily_closed_trades if t['profit_pct'] > 0])
    losses = len([t for t in daily_closed_trades if t['profit_pct'] < 0])
    draws = len([t for t in daily_closed_trades if t['profit_pct'] == 0])
    
    durations = [(t['close_time'] - t['open_time']).total_seconds() for t in daily_closed_trades]
    avg_dur = str(timedelta(seconds=int(sum(durations)/total))).split('.')[0]
    
    report = "📊 *التقرير الختامي اليومي* \n\n"
    report += "`العملة | دخول | خروج | نتيجة | مدة` \n"
    report += "`-----------------------------------` \n"
    for t in daily_closed_trades:
        dur = str(t['close_time'] - t['open_time']).split('.')[0]
        report += f"`{t['symbol'][:5]:<5} | {t['entry']:.3f} | {t['exit']:.3f} | {t['profit_pct']:+.1f}% | {dur}` \n"
    
    report += "`-----------------------------------` \n\n"
    report += f"✅ ناجحة: `{wins}` | ➖ متعادلة: `{draws}` \n"
    report += f"🛑 خاسرة: `{losses}` | 🎯 نجاح: `{(wins/total)*100:.1f}%` \n"
    report += f"⏱️ معدل التوقيت: `{avg_dur}` \n"
    report += f"📈 صافي الربح: `{sum([t['profit_usdt'] for t in daily_closed_trades]):+.2f}$` \n"
    report += f"💰 الرصيد: `{VIRTUAL_BALANCE:.2f}$`"
    
    send_telegram_to_all(report)
    daily_closed_trades = []

# --- 6. المنطق الرئيسي (Loop) ---

def run_trading_logic():
    global VIRTUAL_BALANCE
    last_daily = datetime.now().date()
    last_2h = datetime.now()
    last_1h = datetime.now()

    send_telegram_to_all("🟢 *انطلق البوت!* \nالبحث جارٍ عن صفقات..")

    while True:
        try:
            now = datetime.now()

            # التقرير اليومي (عند تغيير التاريخ)
            if now.date() > last_daily:
                send_daily_summary()
                last_daily = now.date()

            # إشعار "نبض البوت" كل ساعة
            if now >= last_1h + timedelta(hours=1):
                send_telegram_to_all(f"📡 *إشعار:* البوت يعمل ويبحث عن فرص.. \n⏰ `{now.strftime('%H:%M')}`")
                last_1h = now

            # تقرير الساعتين
            if now >= last_2h + timedelta(hours=2):
                send_open_trades_report()
                last_2h = now

            # مسح السوق والدخول
            symbols = get_top_gainers()
            if len(active_trades) < MAX_TRADES:
                for symbol in symbols:
                    if symbol in [t['symbol'] for t in active_trades] or len(active_trades) >= MAX_TRADES: continue
                    data = get_indicators(symbol)
                    if data is not None and data['rsi'] <= 45 and data['c'] <= data['ma']:
                        entry_amt = VIRTUAL_BALANCE * PERCENT_PER_TRADE
                        new_t = {
                            'symbol': symbol, 'entry_price': data['c'], 'cost': entry_amt,
                            'target': data['c'] * TARGET_PROFIT, 'stop': data['c'] * STOP_LOSS,
                            'open_time': datetime.now()
                        }
                        active_trades.append(new_t)
                        VIRTUAL_BALANCE -= entry_amt
                        send_telegram_to_all(f"🔔 *شراء:* `{symbol}` بسعر `{data['c']:.4f}`")

            # مراقبة الإغلاق
            if active_trades:
                tickers = exchange.fetch_tickers()
                for t in active_trades[:]:
                    p_now = tickers[t['symbol']]['last']
                    if p_now >= t['target'] or p_now <= t['stop']:
                        is_win = p_now >= t['target']
                        p_usdt = t['cost'] * (0.04 if is_win else -0.02)
                        VIRTUAL_BALANCE += (t['cost'] + p_usdt)
                        
                        daily_closed_trades.append({
                            'symbol': t['symbol'], 'entry': t['entry_price'], 'exit': p_now,
                            'profit_pct': 4.0 if is_win else -2.0, 'profit_usdt': p_usdt,
                            'open_time': t['open_time'], 'close_time': datetime.now()
                        })
                        active_trades.remove(t)
                        send_telegram_to_all(f"{'✨' if is_win else '🛑'} *إغلاق:* `{t['symbol']}` | `{p_usdt:+.2f}$`")

            time.sleep(45)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(20)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    run_trading_logic()
