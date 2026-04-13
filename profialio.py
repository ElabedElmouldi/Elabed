portfolio = {
    "balance": 1000,
    "positions": []
}

def add_trade(symbol, entry, size):
    portfolio["positions"].append({
        "symbol": symbol,
        "entry": entry,
        "size": size
    })

def close_trade(symbol, exit_price):
    for p in portfolio["positions"]:
        if p["symbol"] == symbol:
            profit = (exit_price - p["entry"]) * p["size"]
            portfolio["balance"] += profit
            portfolio["positions"].remove(p)
            return profit
