
import numpy as np
from sklearn.ensemble import RandomForestClassifier

class AIModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=500)

    def train(self, X, y):
        self.model.fit(X, y)

    def predict(self, x):
        prob = self.model.predict_proba([x])[0][1]
        return prob
