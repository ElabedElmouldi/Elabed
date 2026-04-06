import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
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

# --- 2. الإعدادات المالية ---
MAX_TRADES = 10
TRADE_VALUE_USD = 100    # قيمة الصفقة الواحدة بالدولار
ACTIVATION_PROFIT = 0.05 
TRAILING_GAP = 0.02      
STOP_LOSS_PCT = 0.04     

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}   
closed_today = []    

# --- 3. وظيفة حساب مدة الصفقة ---
def calculate_duration(start_time_str):
    start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
    now_dt = datetime.strptime(datetime.now().strftime('%H:%M:%S'), '%H:%M:%S')
    duration = now_dt - start_dt
    if duration.days < 0: # لمعالجة الصفقات التي تعبر منتصف الليل
        duration += timedelta(days=1)
    
    mins, secs = divmod(duration.seconds, 60)
    hours, mins = divmod(mins, 60)
    
    if hours > 0:
        return f"{hours} ساعة و {mins} دقيقة"
    return f"{mins} دقيقة و {secs} ثانية"

# --- 4. محرك المراقبة والتتبع (10 ثوانٍ) ---
def monitor_thread():
    while True:
        try:
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                trade = active_trades[symbol]
                
                if cp > trade['highest_price']:
                    active_trades[symbol]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                highest = active_trades[symbol]['highest_price']
                drop = (highest - cp) / highest
                
                exit_triggered = False
                if gain <= -STOP_LOSS_PCT or (gain >= ACTIVATION_PROFIT and drop >= TRAILING_GAP):
                    exit_triggered = True

                if exit_triggered:
                    pnl_val = gain * 100
                    duration = calculate_duration(trade['time'])
                    
                    # إشعار الخروج المعدل
                    exit_msg = (
                        f"🏁 *إشعار خروج من صفقة*\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `{symbol}`\n"
                        f"📥 *سعر الدخول:* `{trade['entry']}`\n"
                        f"📤 *سعر الخروج:* `{cp}`\n"
                        f"📊 *النتيجة:* `{pnl_val:+.2f}%`\n"
                        f"⏳ *مدة الصفقة:* `{duration}`\n"
                        f"━━━━━━━━━━━━━━"
                    )
                    send_telegram(exit_msg)
                    
                    closed_today.append({
                        'symbol': symbol, 'pnl': pnl_val, 
                        'time_in': trade['time'], 'time_out': datetime.now().strftime('%H:%M')
                    })
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(5)

# --- 5. المحرك الرئيسي والمسح ---
def main_engine():
    send_telegram("🚀 *Sniper v16.6 Online*\nتم تعديل نظام الإشعارات وحساب المدة.")
    last_scan = datetime.now() - timedelta(minutes=15)
    
    while True:
        try:
            now = datetime.now()
            
            # المسح التوربيني (900 عملة)
            if now >= last_scan + timedelta(minutes=10):
                tickers = exchange.fetch_tickers()
                all_symbols = [s for s in tickers.keys() if '/USDT' in s]
                targets = sorted(all_symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:900]
                
                for s in targets:
                    if len(active_trades) < MAX_TRADES and s not in active_trades:
                        # [منطق تحليل v20]
                        bars = exchange.fetch_ohlcv(s, timeframe='15m', limit=30)
                        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                        if df['c'].iloc[-1] > df['c'].ewm(span=20).mean().iloc[-1] * 1.02: # شرط مبسط كمثال
                            p = tickers[s]['last']
                            start_time = now.strftime('%H:%M:%S')
                            active_trades[s] = {'entry': p, 'highest_price': p, 'time': start_time}
                            
                            # إشعار الدخول المعدل
                            entry_msg = (
                                f"🔔 *إشعار دخول صفقة*\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"🪙 *العملة:* `{s}`\n"
                                f"💰 *سعر الدخول:* `{p}`\n"
                                f"⏰ *وقت الدخول:* `{start_time}`\n"
                                f"💵 *قيمة الصفقة:* `${TRADE_VALUE_USD}`\n"
                                f"━━━━━━━━━━━━━━"
                            )
                            send_telegram(entry_msg)
                    time.sleep(0.04)
                last_scan = now
            time.sleep(30)
        except: time.sleep(10)

if __name__ == "__main__":
    app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    Thread(target=monitor_thread).start()
    main_engine()
