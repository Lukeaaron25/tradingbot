print("✅ RUNNING CORRECT run_bot.py FILE")


import alpaca_trade_api as tradeapi
import pandas as pd
import time
import os
import json
from datetime import datetime, timedelta
from config import *
from utils import calculate_ema, calculate_rsi, average_volume, calculate_slope

api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

POSITION_FILE = 'position.json'
TRADE_LOG_FILE = 'trades.csv'

def load_position():
    if os.path.exists(POSITION_FILE):
        with open(POSITION_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_position(data):
    with open(POSITION_FILE, 'w') as f:
        json.dump(data, f)

def reset_position():
    if os.path.exists(POSITION_FILE):
        os.remove(POSITION_FILE)

def log_trade(entry_time, exit_time, side, entry_price, exit_price, pnl):
    exists = os.path.exists(TRADE_LOG_FILE)
    with open(TRADE_LOG_FILE, 'a') as f:
        if not exists:
            f.write("entry_time,exit_time,side,entry_price,exit_price,pnl\n")
        f.write(f"{entry_time},{exit_time},{side},{entry_price},{exit_price},{pnl}\n")

def check_daily_limits():
    try:
        today = datetime.now().date().isoformat()
        activities = api.get_activities()
        daily_trades = [act for act in activities if act.symbol == SYMBOL and act.transaction_time.date().isoformat() == today]
        trade_count = len([t for t in daily_trades if t.side in ['buy', 'sell']])
        pnl = sum([float(a.realized_pl) for a in daily_trades if hasattr(a, 'realized_pl')])
        return trade_count, pnl
    except:
        return 0, 0

def get_data(symbol, timeframe='1Min', limit=30):
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        client = StockHistoricalDataClient(API_KEY, API_SECRET)

        end = datetime.now()
        start = end - timedelta(minutes=limit)

        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(timeframe, TimeFrameUnit.Minute),
            start=start,
            end=end
        )

        bars = client.get_stock_bars(request_params).df
        df = bars.reset_index().tail(limit)
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Data error: {e}")
        return pd.DataFrame()

def close_position():
    try:
        api.close_position(SYMBOL)
        print("Position closed.")
    except Exception as e:
        print(f"Close error: {e}")

def place_order(side, qty, price):
    try:
        api.submit_order(
            symbol=SYMBOL,
            qty=qty,
            side=side,
            type='limit',
            limit_price=round(price, 2),
            time_in_force='gtc'
        )
        print(f"{side.upper()} order placed at {price}")
    except Exception as e:
        print(f"Order error: {e}")

def trade():
    now = datetime.now()
    position = load_position()

    if 'last_exit' in position:
        last_exit = datetime.fromisoformat(position['last_exit'])
        if (now - last_exit).total_seconds() < TRADE_COOLDOWN_MINUTES * 60:
            print("Cooldown active.")
            return

    trade_count, daily_pnl = check_daily_limits()
    if trade_count >= MAX_TRADES_PER_DAY or daily_pnl <= -DAILY_LOSS_LIMIT:
        print("Daily limit reached.")
        return

    df_1m = get_data(SYMBOL, '1Min', 30)
    df_5m = get_data(SYMBOL, '5Min', 30)

    if df_1m.empty or df_5m.empty:
        print("Data unavailable.")
        return

    df_1m['ema9'] = calculate_ema(df_1m)
    df_1m['rsi'] = calculate_rsi(df_1m)
    df_1m['avg_volume'] = average_volume(df_1m)

    df_5m['ema50'] = calculate_ema(df_5m, 50)
    df_5m['slope50'] = calculate_slope(df_5m['ema50'])

    last = df_1m.iloc[-1].copy()
    print("📊 Raw last row values:")
    for k, v in last.items():
        print(f"  {k}: {repr(v)}")

    numeric_keys = ['close', 'open', 'ema9', 'rsi', 'volume', 'avg_volume']
    for key in numeric_keys:
        try:
            val = last[key]
            if pd.isna(val) or str(val).strip() in ['', 'None', 'nan', 'NaN']:
                raise ValueError(f"Missing or empty value for {key}")
            val = float(val) if isinstance(val, (int, float)) else float(str(val).replace(',', '').strip())
            last[key] = val
        except Exception as e:
            print(f"❌ Data conversion error for '{key}': {e}")
            return

    slope = float(df_5m['slope50'].iloc[-1])
    side = position.get('side')

    qty = position.get('qty', 0)
    entry_price = position.get('entry_price', 0)
    buying_power = float(api.get_account().cash)
    trade_qty = int((buying_power * POSITION_SIZE_PCT) / last['close'])

    if not side:
        if last['close'] > last['open'] and last['close'] > last['ema9'] and last['rsi'] < 65 and last['volume'] > last['avg_volume'] and slope > 0:
            price = last['close'] * 1.001
            place_order('buy', trade_qty, price)
            save_position({'side': 'long', 'entry_price': price, 'qty': trade_qty, 'high': price, 'entry_time': now.isoformat()})

        elif last['close'] < last['open'] and last['close'] < last['ema9'] and last['rsi'] > 55 and last['volume'] > last['avg_volume'] and slope < 0:
            price = last['close'] * 0.999
            place_order('sell', trade_qty, price)
            save_position({'side': 'short', 'entry_price': price, 'qty': trade_qty, 'low': price, 'entry_time': now.isoformat()})

    elif side == 'long':
        position['high'] = max(position['high'], last['close'])
        trail_stop = position['high'] * (1 - TRAILING_STOP_PCT)
        print(f"➡️ [LONG] Comparing last['close'] = {last['close']} (type: {type(last['close'])}) to trail_stop = {trail_stop}")
        last_close = float(last['close'])
        if last_close <= trail_stop or last_close < last['ema9']:
            close_position()
            exit_price = last['close']
            pnl = (exit_price - entry_price) * qty
            log_trade(position['entry_time'], now.isoformat(), side, entry_price, exit_price, pnl)
            reset_position()
            save_position({'last_exit': now.isoformat()})

    elif side == 'short':
        position['low'] = min(position['low'], last['close'])
        trail_stop = position['low'] * (1 + TRAILING_STOP_PCT)
        print(f"➡️ [SHORT] Comparing last['close'] = {last['close']} (type: {type(last['close'])}) to trail_stop = {trail_stop}")
        last_close = float(last['close'])
        if last_close >= trail_stop or last_close > last['ema9']:
            close_position()
            exit_price = last['close']
            pnl = (entry_price - exit_price) * qty
            log_trade(position['entry_time'], now.isoformat(), side, entry_price, exit_price, pnl)
            reset_position()
            save_position({'last_exit': now.isoformat()})

if __name__ == '__main__':
    while True:
        try:
            trade()
        except Exception as e:
            print(f"Runtime error: {e}")
        time.sleep(60)
