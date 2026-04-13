def position_size(capital, risk=0.02):
    return capital * risk

def stop_loss(price):
    return price * 0.98

def take_profit(price):
    return price * 1.05
