import time
from ai_model import AIModel
from strategy import decision
from risk import position_size
from portfolio import add_trade

ai = AIModel()
capital = 1000

def extract_features(price):
    return [price, price * 0.5, price * 0.2]

def run(price_feed):
    while True:
        for symbol, price in price_feed.items():

            x = extract_features(price)
            prob = ai.predict(x)

            action = decision(prob)

            if action == "STRONG_BUY":
                size = position_size(capital)
                add_trade(symbol, price, size)

        time.sleep(5)
