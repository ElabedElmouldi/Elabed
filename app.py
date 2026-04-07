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
FRIENDS_IDS = ["5067771509", "-1003692815602"]
exchange = ccxt.binance({'enableRateLimit': True})

app = Flask(__name__)

# مخزن العمليات الافتراضية لمراقبة الصفقات المفتوحة
virtual_trades = {}

@app.route('/')
def health_check():
    return "Dynamic Strategy Bot v530 is Online!", 200

def send_telegram(msg):
    for cid in FRIENDS_IDS:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload = {"chat_id": cid, "text": msg, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# --- 2. محرك الحسابات والمؤشرات ---

def get_atr(df, period=14):
    """حساب متوسط المدى الحقيقي لتحديد أهداف ديناميكية"""
    df = df.copy()
    df['h-l'] = df['h'] - df['l']
    df['h-pc'] = abs(df['h'] - df['c'].shift(1))
    df['l-pc'] = abs(df['l'] - df['c'].shift(1))
    df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
    return df['tr'].rolling(window=period).mean().iloc[-1]

def get_scores(symbol):
    try:
        # جلب بيانات 15 دقيقة (كافية للتحليل والـ ATR)
        ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        cp = df['c'].iloc[-1]
        
        # S1: السيولة (Momentum) - مقارنة الفوليوم الحالي بالمتوسط
        s1 = round((df['v'].iloc[-1] / df['v'].tail(20).mean()) * 5, 2)
        
        # S2: الاختراق (Breakout) - القرب من قمة 24 ساعة
        high_max = df['h'].max()
        s2 = round(20 if cp >= high_max else (cp/high_max)*10, 2)
        
        # S3: الاتجاه (Trend) - السعر فوق متوسط EMA20
        ema = df['c'].ewm(span=20).mean().iloc[-1]
        s3 = 15 if cp > ema else 0
        
        # S4: القوة النسبية (Relative Strength) - نسبة التغير الصافي
        change = ((cp - df['o'].iloc[0]) / df['o'].iloc[0]) * 100
        s4 = round(change * 4, 2)
        
        # S5: الضغط (Volatility Squeeze) - انضغاط السعر للانفجار
        std = df['c'].tail(20).std()
        s5 = round(1 / (std / cp + 1e-9), 2)
        
        atr = get_atr(df)
        
        return {
            'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 
            'total': s1+s2+s3+s4+s5, 'price': cp, 'atr': atr
        }
    except: return None

# --- 3. نظام مراقبة وإغلاق الصفقات ---

def monitor_loop():
    """مراقبة الصفقات المفتوحة لحظياً لتنفيذ الخروج"""
    while True:
        try:
            for symbol in list(virtual_trades.keys()):
                trade = virtual_trades[symbol]
                ticker = exchange.fetch_ticker(symbol)
                cp = ticker['last']
                
                # شروط الخروج الديناميكية
                hit_tp = cp >= trade['tp']
                hit_sl = cp <= trade['sl']
                
                if hit_tp or hit_sl:
                    res_pct = ((cp - trade['entry']) / trade['entry']) * 100
                    duration = datetime.now() - trade['time']
                    status = "✅ جني أرباح" if hit_tp else "❌ وقف خسارة"
                    
                    report = (
                        f"🏁 *تقرير إغلاق صفقة*\n\n"
                        f"🪙 العملة: `{symbol}`\n"
                        f"📊 النتيجة: `{res_pct:+.2f}%` ({status})\n"
                        f"💰 سعر الخروج: `{cp}`\n"
                        f"⏱️ مدة الصفقة: `{str(duration).split('.')[0]}`"
                    )
                    send_telegram(report)
                    del virtual_trades[symbol]
            time.sleep(20) # فحص كل 20 ثانية
        except Exception as e:
            print(f"Monitor Loop Error: {e}")
            time.sleep(10)

# --- 4. رادار المسح واتخاذ القرار ---

def radar_loop():
    send_telegram("🛰️ *تم تشغيل الرادار الخماسي (v530)*\nالوضع: إجماع الأغلبية + أهداف ATR")
    while True:
        try:
            tickers = exchange.fetch_tickers()
            # اختيار العملات التي تزيد سيولتها عن 15 مليون دولار لضمان المصداقية
            targets = [s for s in tickers if s.endswith('/USDT') and tickers[s].get('quoteVolume', 0) > 15000000][:100]
            
            with ThreadPoolExecutor(max_workers=10) as exec:
                results = list(filter(None, exec.map(get_scores, targets)))
            
            # استخراج أفضل 10 عملات في كل استراتيجية لعمل التصويت
            L1 = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            L2 = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            L3 = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]
            L4 = sorted(results, key=lambda x: x['s4'], reverse=True)[:10]
            L5 = sorted(results, key=lambda x: x['s5'], reverse=True)[:10]

            # تجميع كل العملات المتصدرة وحساب تكرارها
            all_tops = [r['symbol'] for L in [L1, L2, L3, L4, L5] for r in L]
            counts = {s: all_tops.count(s) for s in set(all_tops)}
            
            # اختيار العملات التي حققت إجماع 4 من 5 على الأقل
            qualified = [s for s, count in counts.items() if count >= 4]

            if qualified:
                for sym in qualified:
                    if sym not in virtual_trades:
                        data = next(r for r in results if r['symbol'] == sym)
                        entry_p = data['price']
                        atr = data['atr']
                        
                        # حساب الأهداف بناءً على تقلب العملة (ATR)
                        # وقف الخسارة = السعر - (1.5 ضعف التقلب)
                        # جني الأرباح = السعر + (3 أضعاف التقلب) لضمان Risk/Reward 1:2
                        sl_p = entry_p - (atr * 1.5)
                        tp_p = entry_p + (atr * 3.0)
                        
                        virtual_trades[sym] = {
                            'entry': entry_p, 'tp': tp_p, 'sl': sl_p, 'time': datetime.now()
                        }
                        
                        msg = (
                            f"🚀 *إشارة دخول ذهبية ({counts[sym]}/5)*\n\n"
                            f"🪙 العملة: `{sym}`\n"
                            f"💰 سعر الدخول: `{entry_p}`\n"
                            f"🎯 الهدف (TP): `{tp_p:.6f}`\n"
                            f"🛡️ الوقف (SL): `{sl_p:.6f}`\n"
                            f"📊 السكور الكلي: `{data['total']:.2f}`"
                        )
                        send_telegram(msg)

            time.sleep(900) # مسح شامل كل 15 دقيقة
        except Exception as e:
            print(f"Radar Loop Error: {e}")
            time.sleep(60)

# --- 5. تشغيل السيرفر ---

if __name__ == "__main__":
    # تشغيل الرادار والمراقب كخيوط خلفية
    Thread(target=radar_loop, daemon=True).start()
    Thread(target=monitor_loop, daemon=True).start()
    
    # تشغيل واجهة الويب لضمان بقاء السيرفر (Render/Heroku) متصلاً
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
