import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import requests
import os

# --- 1. إعدادات التلجرام ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]

def send_telegram(message):
    for chat_id in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. الإعدادات المالية والفلترة ---
MAX_TRADES = 10
TRADE_AMOUNT = 100
TAKE_PROFIT_PCT = 0.03
STOP_LOSS_PCT = 0.03

# قائمة الاستبعاد (العملات الكبيرة والمستقرة)
STABLE_AND_BIG = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'LTC/USDT', 'ADA/USDT',
    'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'DAI/USDT', 'USDE/USDT', 'PYUSD/USDT', 'EUR/USDT'
]

exchange = ccxt.binance({'enableRateLimit': True})
active_trades = {}
scan_index = 0 # مؤشر الدوران للمجموعات

# --- 3. محرك المسح الدوّار (The Cyclic Scanner) ---

def explosion_logic(symbol):
    """ تحليل فني سريع لرصد الانفجار """
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=30)
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        # مؤشر قوة السيولة
        vol_current = df['v'].iloc[-1]
        vol_avg = df['v'].iloc[-15:-1].mean()
        
        score = 0
        if vol_current > vol_avg * 2: score += 5  # انفجار فوليوم
        if df['c'].iloc[-1] > df['o'].iloc[-1] * 1.015: score += 3 # صعود > 1.5%
        
        return score if score >= 5 else None
    except: return None

def get_600_filtered_symbols():
    """ جلب وترتيب العملات حسب السيولة مع استبعاد الكبيرة والمستقرة """
    try:
        tickers = exchange.fetch_tickers()
        # فلترة العملات: يجب أن تكون USDT، ليست في القائمة السوداء، وليست عملة مستقرة (بحث بالاسم)
        filtered = [
            s for s in tickers.keys() 
            if '/USDT' in s 
            and s not in STABLE_AND_BIG 
            and 'USD' not in s.split('/')[0] # استبعاد أي عملة فيها كلمة USD
        ]
        # ترتيب حسب حجم التداول 24 ساعة (من الأعلى للأقل)
        sorted_symbols = sorted(filtered, key=lambda x: tickers[x]['quoteVolume'], reverse=True)
        return sorted_symbols[:600]
    except: return []

# --- 4. نظام التقارير والعمليات ---

def run_cyclic_scan():
    global scan_index, active_trades
    all_symbols = get_600_filtered_symbols()
    if not all_symbols: return
    
    # تقسيم 600 عملة إلى 4 مجموعات (0-150, 150-300, 300-450, 450-600)
    start = scan_index * 150
    end = start + 150
    current_group = all_symbols[start:end]
    
    found_opportunities = []
    for s in current_group:
        if s in active_trades: continue
        score = explosion_logic(s)
        if score:
            found_opportunities.append((s, score))
            # فتح صفقة إذا كانت الإشارة قوية جداً
            if score >= 8 and len(active_trades) < MAX_TRADES:
                price = exchange.fetch_ticker(s)['last']
                active_trades[s] = {'entry': price}
                send_telegram(f"🚀 *دخول آلي:* `{s}`\nالسعر: `{price}`")

    # إرسال تقرير الرادار (كل 15 دقيقة)
    radar_text = f"🛰️ *رادار الانفجار (المجموعة {scan_index+1}/4)*\n"
    radar_text += f"🔍 تم فحص عملات الترتيب من `{start}` إلى `{end}`\n"
    if found_opportunities:
        # ترتيب حسب الأقوى
        found_opportunities.sort(key=lambda x: x[1], reverse=True)
        for s, sc in found_opportunities[:5]:
            radar_text += f"🔥 `{s}` | القوة: `{sc}/10` \n"
    else:
        radar_text += "_لا توجد انفجارات في هذه المجموعة حالياً._"
    
    send_telegram(radar_text)
    
    # تحديث المؤشر للدورة القادمة
    scan_index = (scan_index + 1) % 4

# --- 5. المحرك التنفيذي ---

def main_engine():
    send_telegram("📡 *v12.6 System Online*\n- مسح 600 عملة دورياً\n- تقارير رادار كل 15 دقيقة")
    
    last_scan_time = datetime.now() - timedelta(minutes=16)

    while True:
        try:
            now = datetime.now()

            # أ. مراقبة الإغلاق (كل 10 ثوانٍ)
            for symbol in list(active_trades.keys()):
                ticker = exchange.fetch_ticker(symbol)
                pnl = (ticker['last'] - active_trades[symbol]['entry']) / active_trades[symbol]['entry']
                
                if pnl >= TAKE_PROFIT_PCT or pnl <= -STOP_LOSS_PCT:
                    status = "✅ ربح" if pnl > 0 else "🛑 وقف"
                    send_telegram(f"{status}: `{symbol}` ({pnl*100:+.2f}%)")
                    del active_trades[symbol]
                    # إرسال حالة المحفظة (اختياري)

            # ب. تشغيل المسح الدوّار كل 15 دقيقة
            if now >= last_scan_time + timedelta(minutes=15):
                run_cyclic_scan()
                last_scan_time = now

            time.sleep(20)
        except Exception as e:
            time.sleep(30)

if __name__ == "__main__":
    app = Flask('')
    @app.route('/')
    def h(): return "Bot v12.6 Cyclic Scanner Active"
    Thread(target=lambda: app.run(host='0.0.0.0', port=5000)).start()
    main_engine()
