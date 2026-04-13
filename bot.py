.,
.import time
import threading

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ws_engine import start_ws, price_data
from ai_model import AIModel
from strategy import decision
from risk import position_size
from portfolio import portfolio, add_trade, close_trade

# ======================
# INIT AI
# ======================
ai = AIModel()
capital = 1000
bot_running = True

# ======================
# TELEGRAM COMMANDS
# ======================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 HEDGE FUND PRO MAX v2 RUNNING")

async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(portfolio))

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = True
    await update.message.reply_text("🚀 BOT STARTED")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    bot_running = False
    await update.message.reply_text("⛔ BOT STOPPED")

# ======================
# FEATURE ENGINE
# ======================
def extract_features(price):
    return [price, price * 0.5, price * 0.2]

# ======================
# TRADING ENGINE
# ======================
def trading_loop():
    global bot_running

    while True:
        if bot_running:

            for symbol, price in price_data.items():

                try:
                    x = extract_features(price)
                    prob = ai.predict(x)

                    action = decision(prob)

                    # ===== BUY =====
                    if action == "STRONG_BUY":
                        size = position_size(capital)
                        add_trade(symbol, price, size)

                    # ===== SELL (hedge/close) =====
                    elif action == "SELL":
                        close_trade(symbol, price)

                except:
                    continue

        time.sleep(5)

# ======================
# START EVERYTHING
# ======================
def main():
    app = Application.builder().token("YOUR_TOKEN").build()

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("start_bot", start_bot))
    app.add_handler(CommandHandler("stop_bot", stop_bot))

    # WebSocket thread
    threading.Thread(target=start_ws, daemon=True).start()

    # Trading loop thread
    threading.Thread(target=trading_loop, daemon=True).start()

    print("🚀 HEDGE FUND PRO MAX v2 STARTED")

    app.run_polling()

# ======================
if __name__ == "__main__":
    main().
