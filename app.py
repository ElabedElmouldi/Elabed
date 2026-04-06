import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات والروابط ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
# الرابط سيتم جلبه تلقائياً من بيئة Render
RENDER_URL = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

# إعدادات الاستراتيجية
MAX_TRADES = 10
TRADE_VALUE_USD = 100
ACTIVATION_PROFIT = 0.03  # تفعيل التتبع عند 3%
TRAILING_GAP = 0.01       # فارق الملاحقة 1%
STOP_LOSS_PCT = 0.035     # وقف الخسارة 3.5%

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_trades = {}    
blacklist_coins = {} 
leaderboard_tracker = {"symbol": None, "count": 0}

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. محرك مراقبة الصفقات (مع إشعار التتبع الجديد) ---

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                trade = active_trades[s]
                
                # تحديث أعلى سعر وصل له السهم منذ الدخول
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drop_from_peak = (trade['highest_price'] - cp) / trade['highest_price']
                
                # --- إضافة إشعار بداية التتبع ---
                if gain >= ACTIVATION_PROFIT and not trade.get('trailing_notified', False):
                    msg = (
                        f"🎯 *تفعيل تتبع السعر (Trailing Active)*\n"
                        f"🪙 العملة: `{s}`\n"
                        f"📈 الربح الحالي: `+{gain*100:.2f}%`\n"
                        f"🛡️ الحالة: تم تأمين الربح وملاحقة القمة الآن."
                    )
                    send_telegram(msg)
                    active_trades[s]['trailing_notified'] = True # لضمان إرسال الإشعار مرة واحدة فقط

                # --- منطق الخروج ---
                exit_now = False
                reason = ""
                
                if gain <= -STOP_LOSS_PCT:
                    exit_now = True; reason = "🛑 وقف الخسارة (SL)"
                elif trade.get('trailing_notified') and drop_from_peak >= TRAILING_GAP:
                    exit_now = True; reason = "💰 جني أرباح (Trailing Exit)"

                if exit_now:
                    pnl = gain * 100
                    final_msg = (
                        f"🏁 *إغلاق صفقة ({reason})*\n"
                        f"🪙 العملة: `{s}`\n"
                        f"📊 النتيجة النهائية: `{pnl:+.2f}%`"
                    )
                    send_telegram(final_msg)
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1)
                    del active_trades[s]
                    
            time.sleep(15) # فحص كل 15 ثانية
        except Exception as e:
            time.sleep(10)

# --- 3. المحرك الرئيسي (المسح والتقرير الدوري) ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🚀 *Sniper v26.0 Online*\nإشعارات التتبع مفعّلة.")
    
    while True:
        try:
            now = datetime.now()
            blacklist_coins = {s: t for s, t in blacklist_coins.items() if now < t}
            
            tickers = exchange.fetch_tickers()
            all_symbols = [s for s in tickers.keys() if '/USDT' in s and 'USD' not in s.split('/')[0]]
            targets = sorted(all_symbols, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:900]
            
            candidates = []
            def process_scan(s):
                if s not in active_trades and s not in blacklist_coins:
                    t = tickers[s]
                    change = t.get('percentage', 0)
                    vol = t.get('quoteVolume', 0)
                    score = 0
                    if vol > 2000000: score += 5
                    if change > 2.0: score += 10
                    if score >= 10:
                        return {'symbol': s, 'score': score, 'price': t['last'], 'change': change}
                return None

            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(executor.map(process_scan, targets))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            # منطق الصدارة الثلاثي
            if top_10:
                current_winner = top_10[0]['symbol']
                if current_winner == leaderboard_tracker["symbol"]:
                    leaderboard_tracker["count"] += 1
                else:
                    leaderboard_tracker["symbol"] = current_winner
                    leaderboard_tracker["count"] = 1

            # إرسال التقرير
            report = f"📋 *تقرير المسح الدوري*\n🏆 المتصدر: `{leaderboard_tracker['symbol']}` ({leaderboard_tracker['count']}/3)\n"
            report += "━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | `{c['change']:+.2f}%` | `{c['score']}/20` \n"
            send_telegram(report)

            # تنفيذ الدخول
            if leaderboard_tracker["count"] >= 3 and len(active_trades) < MAX_TRADES:
                best = top_10[0]
                s, p = best['symbol'], best['price']
                # تهيئة الصفقة مع إضافة مفتاح الإشعار
                active_trades[s] = {
                    'entry': p, 
                    'highest_price': p, 
                    'time': now.strftime('%H:%M:%S'),
                    'trailing_notified': False # مهم جداً للإشعار الجديد
                }
                send_telegram(f"🚀 *دخول مؤكد (3/3):* `{s}` بسعر `{p}`")
                leaderboard_tracker = {"symbol": None, "count": 0}

            time.sleep(600)
        except: time.sleep(30)

# --- 4. تشغيل السيرفر ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
