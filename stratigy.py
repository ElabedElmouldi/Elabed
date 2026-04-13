
def decision(prob):
    if prob > 0.8:
        return "STRONG_BUY"
    elif prob > 0.65:
        return "BUY"
    elif prob < 0.3:
        return "SELL"
    return "HOLD"
