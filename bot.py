import os
import time
import threading
import random

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ======================
# CONFIG
# ======================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN:
    print("❌ TELEGRAM_TOKEN missing")
    exit()

# ======================
# BOT STATE
# ======================
bot_running = True
capital = 1000
risk = 0.02

open_trades = []
closed_trades = []

# ======================
# SEND MESSAGE
# ======================
def send(msg):
    if not CHAT_ID:
        return
    import requests
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

# ======================
# MARKET SCANNER (DEMO)
# ======================
def scan_market():
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

# ======================
# TRADING LOOP
# ======================
def trading_loop():
    global bot_running

    while True:
        if bot_running:
            for sym in scan_market():

                if len(open_trades) < 5:
                    price = 100 + random.randint(-5, 5)

                    open_trades.append({
                        "symbol": sym,
                        "entry": price,
                        "type": "BUY"
                    })

                    send(f"🟢 OPEN TRADE: {sym} @ {price}")

        time.sleep(10)

# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 PRO BOT STARTED")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
🧠 STATUS

🟢 Running: {bot_running}
💰 Capital: {capital}
⚙️ Risk: {risk*100}%
📂 Open Trades: {len(open_trades)}
📁 Closed Trades: {len(closed_trades)}
"""
    await update.message.reply_text(msg)

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = True
    await update.message.reply_text("🟢 Bot Started")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = False
    await update.message.reply_text("🔴 Bot Stopped")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0]
    price = 100

    open_trades.append({
        "symbol": symbol,
        "entry": price,
        "type": "BUY"
    })

    await update.message.reply_text(f"🟢 BUY {symbol} @ {price}")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0]

    await update.message.reply_text(f"🔴 SELL SIGNAL {symbol}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0]

    global open_trades
    open_trades = [t for t in open_trades if t["symbol"] != symbol]

    await update.message.reply_text(f"❌ CLOSED {symbol}")

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not open_trades:
        await update.message.reply_text("No open trades")
        return

    msg = "📂 OPEN TRADES:\n\n"
    for t in open_trades:
        msg += f"{t['symbol']} @ {t['entry']}\n"

    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💰 Balance: {capital}")

async def set_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global risk
    risk = float(context.args[0]) / 100
    await update.message.reply_text(f"⚙️ Risk set to {risk*100}%")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0]
    decision = random.choice(["BUY", "SELL", "HOLD"])

    await update.message.reply_text(f"🧠 AI SIGNAL {symbol}: {decision}")

# ======================
# MAIN
# ======================
def main():
    app = Application.builder().token(TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("start_bot", start_bot))
    app.add_handler(CommandHandler("stop_bot", stop_bot))

    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("close", close))

    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("set_risk", set_risk))
    app.add_handler(CommandHandler("signal", signal))

    # background trading
    threading.Thread(target=trading_loop, daemon=True).start()

    print("🚀 PRO BOT RUNNING...")
    send("🤖 PRO BOT STARTED")

    app.run_polling()

# ======================
if __name__ == "__main__":
    main()
