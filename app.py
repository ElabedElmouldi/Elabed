import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

# إعدادات الاستراتيجية
MAX_TRADES = 10
ACTIVATION_PROFIT = 0.03 
TRAILING_GAP = 0.01      
STOP_LOSS_PCT = 0.035    

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. دوال الحسابات التقنية اليدوية ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

# --- 3. نظام حساب السكور (النقاط) ---

def calculate_total_score(symbol):
    """حساب نقاط القوة للعملة - المجموع الأقصى 20 نقطة"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        score = 0
        
        # 1. نقاط RSI (حتى 5 نقاط)
        df['rsi'] = calculate_rsi(df['c'])
        rsi = df['rsi'].iloc[-1]
        if 50 < rsi < 65: score += 5  # زخم صاعد مثالي
        elif 65 <= rsi < 75: score += 3 # قريب من التشبع
        
        # 2. نقاط المتوسطات EMA (حتى 5 نقاط)
        df['ema20'] = calculate_ema(df['c'], 20)
        df['ema50'] = calculate_ema(df['c'], 50)
        if df['c'].iloc[-1] > df['ema20'].iloc[-1] > df['ema50'].iloc[-1]:
            score += 5 # ترتيب اتجاه صاعد قوي
        elif df['c'].iloc[-1] > df['ema20'].iloc[-1]:
            score += 2 # صعود بسيط
            
        # 3. نقاط السيولة (حتى 5 نقاط)
        avg_vol = df['v'].tail(20).mean()
        current_vol = df['v'].iloc[-1]
        if current_vol > avg_vol * 2: score += 5 # انفجار في السيولة
        elif current_vol > avg_vol * 1.2: score += 3 # سيولة جيدة
            
        # 4. نقاط الزخم السعري (حتى 5 نقاط)
        change = ((df['c'].iloc[-1] - df['o'].iloc[-1]) / df['o'].iloc[-1]) * 100
        if 2.0 < change < 5.0: score += 5 # صعود حقيقي متزن
        elif 0.5 < change <= 2.0: score += 2 # بداية تحرك
            
        return score, df['c'].iloc[-1], change
    except:
        return 0, 0, 0

# --- 4. المحرك الرئيسي (المسح والترتيب والدخول) ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🛰️ *تم تشغيل رادار السكور v31.0*\nبدء فحص 900 عملة واختيار النخبة...")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            tickers = exchange.fetch_tickers()
            all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
            # ترشيح أولي بناءً على السيولة لتسريع المسح
            targets = sorted(all_symbols, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:900]
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    if tickers[s].get('quoteVolume', 0) > 1000000:
                        score, price, chg = calculate_total_score(s)
                        if score > 0:
                            return {'symbol': s, 'score': score, 'price': price, 'change': chg}
                return None

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(process_scan, targets))
                candidates = [r for r in results if r]

            # 📊 ترتيب القائمة حسب السكور الأعلى
            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # منطق الصدارة لـ 3 مرات متتالية
            entry_signal = False
            if top_10:
                current_winner = top_10[0]['symbol']
                if current_winner == leaderboard_tracker["symbol"]:
                    leaderboard_tracker["count"] += 1
                else:
                    leaderboard_tracker["symbol"] = current_winner
                    leaderboard_tracker["count"] = 1
                
                if leaderboard_tracker["count"] >= 3:
                    entry_signal = True

            # 📝 إرسال التقرير الدوري بـ "سكور" كل عملة
            report = f"📋 *تقرير أفضل العملات (حسب السكور)*\n⏰ `{now.strftime('%H:%M:%S')}`\n"
            report += "━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
                report += f"{emoji} `{c['symbol']}` | سكور: *{c['score']}/20* | `{c['change']:+.2f}%` \n"
            report += "━━━━━━━━━━━━━━\n"
            report += f"🏆 المتصدر الحالي: `{leaderboard_tracker['symbol']}`\n🔄 تكرار الصدارة: `{leaderboard_tracker['count']}/3`"
            send_telegram(report)

            # تنفيذ الدخول عند التأكيد الثلاثي
            if entry_signal and len(active_trades) < MAX_TRADES:
                best = top_10[0]
                # شرط إضافي: يجب أن يكون السكور في المرة الثالثة قوي (مثلاً > 12)
                if best['score'] >= 12:
                    s, p = best['symbol'], best['price']
                    active_trades[s] = {'entry': p, 'highest_price': p, 'time': now.strftime('%H:%M:%S'), 'trailing_notified': False}
                    send_telegram(f"🚀 *دخول استراتيجي:* تم فتح صفقة في `{s}` لأنها تصدرت القائمة بـ 3 مسحات متتالية بسكور `{best['score']}`.")
                    leaderboard_tracker = {"symbol": None, "count": 0}

            time.sleep(600) # مسح كل 10 دقائق
        except: time.sleep(30)

# --- (بقية الأكواد monitor_trades و Flask تبقى كما هي لضمان عمل السيرفر والرصيد) ---

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s); cp = ticker['last']; trade = active_trades[s]
                if cp > trade.get('highest_price', 0): active_trades[s]['highest_price'] = cp
                gain = (cp - trade['entry']) / trade['entry']
                drop = (trade['highest_price'] - cp) / trade['highest_price']
                if gain >= ACTIVATION_PROFIT and not trade.get('trailing_notified', False):
                    send_telegram(f"🎯 *تأمين:* `{s}` ربح `+{gain*100:.2f}%` وبدء التتبع 🛡️"); active_trades[s]['trailing_notified'] = True
                exit_now = False
                if gain <= -STOP_LOSS_PCT: exit_now = True; res = "🛑 SL"
                elif trade.get('trailing_notified') and drop >= TRAILING_GAP: exit_now = True; res = "💰 TP"
                if exit_now:
                    bal = exchange.fetch_balance()['total'].get('USDT', 0)
                    send_telegram(f"🏁 *إغلاق:* `{s}` | النتيجة: `{gain*100:+.2f}%` \n💰 المحفظة: `${bal:.2f}`")
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1); del active_trades[s]
            time.sleep(15)
        except: time.sleep(10)

app = Flask(__name__)
@app.route('/')
def home(): return "Scanner Online"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
