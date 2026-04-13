def backtest(prices):
    balance = 1000

    for i in range(1, len(prices)):
        if prices[i] > prices[i-1]:
            balance *= 1.01
        else:
            balance *= 0.99

    return balance
