import ccxt
import pandas as pd
import numpy as np
import time
import json
import os
from datetime import datetime
from flask import Flask
from threading import Thread
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 1. الإعدادات ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
FRIENDS_IDS = ["5067771509", "2107567005"]
DATA_FILE = "pro_trader_v500.json"
exchange = ccxt.binance({'enableRateLimit': True})

SCAN_INTERVAL = 900 
DAILY_GOAL_PCT = 3.0
MAX_VIRTUAL_TRADES = 5

# --- 2. دوال التحليل الفني المتقدمة ---

def calculate_adx(df, period=14):
    """حساب مؤشر قوة الاتجاه ADX"""
    df = df.copy()
    df['h-l'] = df['h'] - df['l']
    df['h-pc'] = abs(df['h'] - df['c'].shift(1))
    df['l-pc'] = abs(df['l'] - df['c'].shift(1))
    df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
    
    df['plus_dm'] = np.where((df['h'] - df['h'].shift(1)) > (df['l'].shift(1) - df['l']), 
                             pmax(df['h'] - df['h'].shift(1), 0), 0)
    df['minus_dm'] = np.where((df['l'].shift(1) - df['l']) > (df['h'] - df['h'].shift(1)), 
                              pmax(df['l'].shift(1) - df['l'], 0), 0)
    
    tr_smooth = df['tr'].rolling(period).mean()
    plus_di = 100 * (df['plus_dm'].rolling(period).mean() / tr_smooth)
    minus_di = 100 * (df['minus_dm'].rolling(period).mean() / tr_smooth)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.rolling(period).mean().iloc[-1]

def pmax(a, b): return np.where(a > b, a, b)

# --- 3. المحرك المطور للاستراتيجيات ---

def get_pro_scores(symbol, btc_change):
    try:
        df_15m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '15m', 100), columns=['t','o','h','l','c','v'])
        cp = df_15m['c'].iloc[-1]
        vol_mean = df_15m['v'].tail(20).mean()
        
        # 1. سيولة الشراء الذكية (Smart Volume)
        rvol = df_15m['v'].iloc[-1] / vol_mean
        close_pos = (cp - df_15m['l'].iloc[-1]) / (df_15m['h'].iloc[-1] - df_15m['l'].iloc[-1])
        s1 = round(rvol * 5 * close_pos, 2) # السكور يقوى إذا كان الإغلاق قرب القمة
        
        # 2. الاختراق الحقيقي (High-Volume Breakout)
        high_24h = df_15m['h'].tail(96).max()
        vol_break = 1.5 if df_15m['v'].iloc[-1] > vol_mean * 2 else 1.0
        s2 = round((20 if cp >= high_24h else (cp/high_24h)*10) * vol_break, 2)
        
        # 3. قوة الترند (ADX Filtered Trend)
        adx = calculate_adx(df_15m)
        ema20 = df_15m['c'].ewm(span=20).mean().iloc[-1]
        s3 = round((15 if (cp > ema20 and adx > 25) else (5 if adx > 25 else 0)), 2)
        
        # 4. القوة النسبية ضد البيتكوين (Relative Strength)
        coin_change = ((cp - df_15m['o'].iloc[-1]) / df_15m['o'].iloc[-1]) * 100
        rel_strength = coin_change - btc_change
        s4 = round(rel_strength * 5, 2)
        
        # 5. انفجار الضغط (Squeeze Breakout)
        std = df_15m['c'].tail(20).std()
        sma = df_15m['c'].tail(20).mean()
        squeeze = (std * 2) / sma
        s5 = round((1 / squeeze) * 2 if cp > sma else 0, 2)
        
        return {'symbol': symbol, 's1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 'price': cp, 'total': s1+s2+s3+s4+s5}
    except: return None

# --- 4. فلتر البيتكوين وإدارة السوق ---

def get_btc_status():
    """تحليل حالة البيتكوين اللحظية"""
    try:
        btc = exchange.fetch_ohlcv('BTC/USDT', '15m', 5)
        change = ((btc[-1][4] - btc[0][1]) / btc[0][1]) * 100
        return change # نسبة التغير في آخر ساعة (4 شموع 15د)
    except: return 0

# --- 5. رادار المسح والإجماع ---

def radar_engine():
    send_telegram("🚀 *تشغيل نسخة المحترف v500.0*\nتحسينات: ADX | Smart Volume | BTC Filter")
    while True:
        try:
            btc_change = get_btc_status()
            
            # حماية البيتكوين: إذا هبط BTC > 1% في 15د، توقف عن الشراء
            if btc_change < -1.5:
                send_telegram("⚠️ *توقف مؤقت:* هبوط حاد في البيتكوين. حماية المحفظة مفعلة.")
                time.sleep(300); continue

            tickers = exchange.fetch_tickers()
            targets = [s for s in tickers if s.endswith('/USDT') and tickers[s].get('quoteVolume', 0) > 10000000] # سيولة > 10 مليون
            targets = sorted(targets, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:100]

            with ThreadPoolExecutor(max_workers=15) as exec:
                results = list(filter(None, exec.map(lambda s: get_pro_scores(s, btc_change), targets)))

            # استخراج القوائم الخمس (أفضل 10)
            L1 = sorted(results, key=lambda x: x['s1'], reverse=True)[:10]
            L2 = sorted(results, key=lambda x: x['s2'], reverse=True)[:10]
            L3 = sorted(results, key=lambda x: x['s3'], reverse=True)[:10]
            L4 = sorted(results, key=lambda x: x['s4'], reverse=True)[:10]
            L5 = sorted(results, key=lambda x: x['s5'], reverse=True)[:10]

            sets = [ {r['symbol'] for r in L} for L in [L1, L2, L3, L4, L5] ]
            common = set.intersection(*sets)

            # إرسال التقارير
            msg = "📊 *رادار المحترف (Top 10):*\n"
            msg += f"🔸 *السيولة:* {', '.join([r['symbol'].split('/')[0] for r in L1[:5]])}...\n"
            msg += f"🔸 *الاختراق:* {', '.join([r['symbol'].split('/')[0] for r in L2[:5]])}...\n"
            msg += f"🔸 *الاتجاه:* {', '.join([r['symbol'].split('/')[0] for r in L3[:5]])}...\n"
            msg += f"🔸 *القوة:* {', '.join([r['symbol'].split('/')[0] for r in L4[:5]])}...\n"
            msg += f"🔸 *الضغط:* {', '.join([r['symbol'].split('/')[0] for r in L5[:5]])}"
            send_telegram(msg)

            if common:
                finalists = sorted([r for r in results if r['symbol'] in common], key=lambda x: x['total'], reverse=True)
                best = finalists[0]
                
                if best['symbol'] not in virtual_trades:
                    # منطق الدخول (كما في النسخ السابقة...)
                    send_telegram(f"🔥 *إجماع احترافي (5/5):* `{best['symbol']}`\nسكور كلي: `{best['total']:.2f}`\nADX قوي + سيولة ذكية ✅")
            
            time.sleep(SCAN_INTERVAL)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(30)

# [باقي دوال الإدارة Flask و monitor_trades تبقى كما هي في v450]
