# utils.py

import pandas as pd

def calculate_ema(data, period=9):
    return data['close'].ewm(span=period, adjust=False).mean()

def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def average_volume(data, window=20):
    return data['volume'].rolling(window=window).mean()

def calculate_slope(series, window=5):
    return series.diff().rolling(window=window).mean()
