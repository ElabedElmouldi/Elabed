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

# إعداد المنصة (تأكد من وضع API Key و Secret في Render لاحقاً)
exchange = ccxt.binance({
    'enableRateLimit': True, 
    'options': {'defaultType': 'spot'}
})

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

def get_wallet_balance():
    """جلب رصيد USDT المتاح والمجموع الكلي للمحفظة"""
    try:
        balance = exchange.fetch_balance()
        total_usdt = balance['total'].get('USDT', 0)
        free_usdt = balance['free'].get('USDT', 0)
        return total_usdt, free_usdt
    except:
        return 0, 0

# --- 2. مراقبة الصفقات وإرسال قيمة المحفظة عند الإغلاق ---

def monitor_trades():
    while True:
        try:
            for s in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(s)
                cp = ticker['last']
                trade = active_trades[s]
                
                if cp > trade.get('highest_price', 0):
                    active_trades[s]['highest_price'] = cp
                
                gain = (cp - trade['entry']) / trade['entry']
                drop_from_peak = (trade['highest_price'] - cp) / trade['highest_price']
                
                # إشعار تفعيل التتبع
                if gain >= ACTIVATION_PROFIT and not trade.get('trailing_notified', False):
                    send_telegram(f"🎯 *تفعيل التتبع:* `{s}` الربح الحالي: `+{gain*100:.2f}%` 🛡️")
                    active_trades[s]['trailing_notified'] = True

                exit_now = False
                reason = ""
                if gain <= -STOP_LOSS_PCT: exit_now = True; reason = "🛑 SL"
                elif trade.get('trailing_notified') and drop_from_peak >= TRAILING_GAP:
                    exit_now = True; reason = "💰 TP"

                if exit_now:
                    pnl = gain * 100
                    # جلب الرصيد المحدث فور الإغلاق
                    total_bal, free_bal = get_wallet_balance()
                    
                    final_msg = (
                        f"🏁 *إغلاق صفقة ({reason})*\n"
                        f"🪙 العملة: `{s}`\n"
                        f"📊 النتيجة: `{pnl:+.2f}%` \n"
                        f"━━━━━━━━━━━━━━\n"
                        f"💰 *حالة المحفظة الآن:*\n"
                        f"💵 الإجمالي: `${total_bal:.2f}`\n"
                        f"🔓 المتاح للتداول: `${free_bal:.2f}`"
                    )
                    send_telegram(final_msg)
                    blacklist_coins[s] = datetime.now() + timedelta(hours=1)
                    del active_trades[s]
                    
            time.sleep(15)
        except: time.sleep(10)

# --- 3. المحرك الرئيسي ---

def main_engine():
    global leaderboard_tracker, blacklist_coins
    send_telegram("🚀 *Sniper v27.0 Online*\nنظام تقرير المحفظة عند الإغلاق مفعّل.")
    
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
                    score = 0
                    if t['quoteVolume'] > 2000000: score += 10
                    if t['percentage'] > 2.0: score += 10
                    if score >= 10:
                        return {'symbol': s, 'score': score, 'price': t['last'], 'change': t['percentage']}
                return None

            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(executor.map(process_scan, targets))
                candidates = [r for r in results if r]

            candidates.sort(key=lambda x: (x['score'], x['change']), reverse=True)
            top_10 = candidates[:10]

            if top_10:
                current_winner = top_10[0]['symbol']
                if current_winner == leaderboard_tracker["symbol"]:
                    leaderboard_tracker["count"] += 1
                else:
                    leaderboard_tracker["symbol"] = current_winner
                    leaderboard_tracker["count"] = 1

            # تقرير المسح
            report = f"📋 *تقرير المسح الدوري*\n🏆 المتصدر: `{leaderboard_tracker['symbol']}` ({leaderboard_tracker['count']}/3)\n"
            report += "━━━━━━━━━━━━━━\n"
            for i, c in enumerate(top_10, 1):
                report += f"{'🥇' if i==1 else '🔹'} `{c['symbol']}` | `{c['change']:+.2f}%` \n"
            send_telegram(report)

            if leaderboard_tracker["count"] >= 3 and len(active_trades) < MAX_TRADES:
                best = top_10[0]
                active_trades[best['symbol']] = {
                    'entry': best['price'], 'highest_price': best['price'], 
                    'time': now.strftime('%H:%M:%S'), 'trailing_notified': False
                }
                send_telegram(f"🚀 *دخول:* `{best['symbol']}` بسعر `{best['price']}`")
                leaderboard_tracker = {"symbol": None, "count": 0}

            time.sleep(600)
        except: time.sleep(30)

# --- التشغيل ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Online"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    Thread(target=monitor_trades).start()
    main_engine()
