import ccxt
import pandas as pd
import numpy as np
import time
import os
import requests
from threading import Thread
from flask import Flask
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات الأساسية ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
exchange = ccxt.binance({'enableRateLimit': True})

# قائمة العملات المستقرة لتجنبها تماماً
STABLE_COINS = [
    'USDT', 'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'EUR', 
    'GBP', 'PAXG', 'AEUR', 'USDP', 'WBTC', 'WETH'
]

app = Flask(__name__)
virtual_trades = {}

@app.route('/')
def health_check():
    return "Clean Sniper Bot v540 is Online!", 200

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 2. المحرك الفني ---

def get_atr(df):
    df = df.copy()
    df['tr'] = pd.concat([df['h']-df['l'], abs(df['h']-df['c'].shift(1)), abs(df['l']-df['c'].shift(1))], axis=1).max(axis=1)
    return df['tr'].rolling(window=14).mean().iloc[-1]

def get_scores(symbol):
    try:
        # التأكد أن العملة ليست مستقرة قبل التحليل
        base_asset = symbol.split('/')[0]
        if base_asset in STABLE_COINS: return None

        ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        
        # الاستراتيجيات الخمس
        s1 = round((df['v'].iloc[-1] / df['v'].tail(20).mean()) * 5, 2) # السيولة
        s2 = round(20 if cp >= df['h'].max() else (cp/df['h'].max())*10, 2) # الاختراق
        ema = df['c'].ewm(span=20).mean().iloc[-1]
        s3 = 15 if cp > ema else 0 # الاتجاه
        change = ((cp - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
        s4 = round(change * 4, 2) # القوة
        std = df['c'].tail(20).std()
        s5 = round(1 / (std / cp + 1e-9), 2) # الضغط
        
        return {
            'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 
            'total': s1+s2+s3+s4+s5, 'price': cp, 'atr': get_atr(df)
        }
    except: return None

# --- 3. إدارة العمليات والرادار ---

def monitor_loop():
    while True:
        try:
            for symbol in list(virtual_trades.keys()):
                trade = virtual_trades[symbol]
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                
                if cp >= trade['tp'] or cp <= trade['sl']:
                    res = ((cp - trade['entry']) / trade['entry']) * 100
                    status = "✅ ربح" if cp >= trade['tp'] else "❌ خسارة"
                    send_telegram(f"🏁 *إغلاق صفقة*\n🪙 `{symbol}`\n📈 النتيجة: `{res:+.2f}%` ({status})\n⏱️ المدة: `{str(datetime.now()-trade['time']).split('.')[0]}`")
                    del virtual_trades[symbol]
            time.sleep(20)
        except: time.sleep(10)

def radar_loop():
    send_telegram("🛡️ *تشغيل الرادار الذكي v540*\nتم استبعاد العملات المستقرة + تفعيل شرط (L1 & L2)")
    while True:
        try:
            tickers = exchange.fetch_tickers()
            # فلترة أولية لاستبعاد المستقرة والسيولة الضعيفة
            targets = [s for s in tickers if s.endswith('/USDT') and 
                       s.split('/')[0] not in STABLE_COINS and 
                       tickers[s].get('quoteVolume', 0) > 15000000][:120]
            
            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(get_scores, targets)))
            
            # ترتيب القوائم
            L1 = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            L2 = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            L3 = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]
            L4 = sorted(results, key=lambda x: x['s4'], reverse=True)[:10]
            L5 = sorted(results, key=lambda x: x['s5'], reverse=True)[:10]

            # تجميع أسماء العملات في كل قائمة
            l1_syms = {r['symbol'] for r in L1}
            l2_syms = {r['symbol'] for r in L2}
            
            all_tops = [r['symbol'] for L in [L1, L2, L3, L4, L5] for r in L]
            counts = {s: all_tops.count(s) for s in set(all_tops)}

            # الشرط الجديد: 4 قوائم على الأقل ويجب أن تشمل L1 و L2
            qualified = [s for s, c in counts.items() if c >= 4 and s in l1_syms and s in l2_syms]

            if qualified:
                for sym in qualified:
                    if sym not in virtual_trades and len(virtual_trades) < 5:
                        data = next(r for r in results if r['symbol'] == sym)
                        atr = data['atr']
                        virtual_trades[sym] = {
                            'entry': data['price'], 
                            'tp': data['price'] + (atr * 3), 
                            'sl': data['price'] - (atr * 1.5), 
                            'time': datetime.now()
                        }
                        send_telegram(f"🚀 *دخول واثق (إجماع {counts[sym]}/5)*\n🪙 `{sym}`\n💰 السعر: `{data['price']}`\n🎯 الهدف: `{virtual_trades[sym]['tp']:.6f}`\n🛡️ الوقف: `{virtual_trades[sym]['sl']:.6f}`")

            time.sleep(900)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(60)

if __name__ == "__main__":
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
