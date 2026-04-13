import os
import time
import threading
import requests

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ======================
# CONFIG (FIXED)
# ======================
TOKEN = os.getenv("8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN:
    print("❌ Missing TELEGRAM_TOKEN")
    print("👉 Add it in Railway Variables")
    exit()

# ======================
# BOT STATE
# ======================
bot_running = True
capital = 1000

open_trades = []
closed_trades = []

# ======================
# SEND MESSAGE
# ======================
def send(msg):
    if not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ======================
# SIMPLE SCANNER
# ======================
def scan_market():
    return ["BTC_USDT", "ETH_USDT"]

# ======================
# TRADING LOOP
# ======================
def trading_loop():
    global bot_running

    while True:
        if bot_running:
            signals = scan_market()

            for sym in signals:
                if len(open_trades) < 5:
                    open_trades.append({
                        "symbol": sym,
                        "entry": 100
                    })
                    send(f"🟢 BUY SIGNAL: {sym}")

        time.sleep(10)

# ======================
# COMMANDS
# ======================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
🧠 BOT STATUS

🟢 Running: {bot_running}
💰 Capital: {capital}
📂 Open Trades: {len(open_trades)}
📁 Closed Trades: {len(closed_trades)}
"""
    await update.message.reply_text(msg)

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = True
    await update.message.reply_text("🚀 Bot Started")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = False
    await update.message.reply_text("⛔ Bot Stopped")

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not open_trades:
        await update.message.reply_text("No open trades")
        return

    msg = ""
    for t in open_trades:
        msg += f"{t['symbol']} @ {t['entry']}\n"

    await update.message.reply_text(msg)

# ======================
# MAIN
# ======================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("start_bot", start_bot))
    app.add_handler(CommandHandler("stop_bot", stop_bot))
    app.add_handler(CommandHandler("portfolio", portfolio))

    threading.Thread(target=trading_loop, daemon=True).start()

    print("🚀 Bot running...")
    send("🤖 Bot started successfully")

    app.run_polling()

# ======================
if __name__ == "__main__":
    main()
