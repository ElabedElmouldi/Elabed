import json
import ccxt
import pandas as pd
import requests
import time
import os
import threading
import http.server
import socketserver
from datetime import datetime

# بيانات البوت الخاصة بك
TELEGRAM_TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

CHAT_ID = "-1003692815602"

exchange = ccxt.binance()
DATA_FILE = 'trading_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"active_trades": [], "completed_trades": [], "last_report_date": ""}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except: pass

def calculate_rsi(series, period=14):
    """حساب مؤشر RSI يدوياً"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_indicators(df):
    """حساب Bollinger Bands و RSI بدون مكتبات خارجية"""
    # حساب المتوسط المتحرك والانحراف المعياري للبولينجر
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper_band'] = df['ma20'] + (df['std'] * 2)
    
    # حساب RSI
    df['rsi'] = calculate_rsi(df['close'])
    return df

def check_signal(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df = calculate_indicators(df)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # شرط الاختراق: السعر الحالي فوق البولينجر العلوي والسابق كان تحته + RSI قوي
        if last['close'] > last['upper_band'] and prev['close'] <= prev['upper_band'] and last['rsi'] > 60:
            return True, last['close']
    except: pass
    return False, 0

def monitor_trades():
    data = load_data()
    updated_active = []
    for trade in data['active_trades']:
        try:
            curr_p = exchange.fetch_ticker(trade['symbol'])['last']
            change = ((curr_p - trade['entry_price']) / trade['entry_price']) * 100
            
            if change >= 5.0:
                trade['result'] = "✅ +5.0%"
                data['completed_trades'].append(trade)
                send_telegram(f"🎯 *هدف محقق!* \nالعملة: `{trade['symbol']}` \nالربح: `+5%`")
            elif change <= -2.5:
                trade['result'] = "❌ -2.5%"
                data['completed_trades'].append(trade)
                send_telegram(f"🛑 *وقف خسارة!* \nالعملة: `{trade['symbol']}` \nالخسارة: `-2.5%`")
            else:
                updated_active.append(trade)
        except: updated_active.append(trade)
    
    data['active_trades'] = updated_active
    save_data(data)

def daily_report():
    data = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    if data['last_report_date'] == today: return

    report = f"📊 *تقرير التداول - {today}*\n\n✅ *المنتهية:* {len(data['completed_trades'])}\n⏳ *المفتوحة:* {len(data['active_trades'])}\n"
    for t in data['completed_trades']:
        report += f"• `{t['symbol']}` {t['result']}\n"
    
    send_telegram(report)
    data['completed_trades'] = []
    data['last_report_date'] = today
    save_data(data)

def main():
    send_telegram("🚀 *البوت يعمل الآن (بدون مكتبة pandas_ta)*")
    while True:
        monitor_trades()
        data = load_data()
        
        tickers = exchange.fetch_tickers()
        symbols = [s for s in tickers if '/USDT' in s and 'UP' not in s and 'DOWN' not in s]
        top_50 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

        for sym in top_50:
            if any(t['symbol'] == sym for t in data['active_trades']): continue
            is_valid, price = check_signal(sym)
            if is_valid:
                data['active_trades'].append({"symbol": sym, "entry_price": price, "date": str(datetime.now())})
                save_data(data)
                send_telegram(f"📥 *دخول جديد:* `{sym}` بسعر `{price}`")

        if datetime.now().hour == 23: daily_report()
        time.sleep(600)

if __name__ == "__main__":
    main()
