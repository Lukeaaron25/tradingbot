# TSLA Trading Bot v3 (Resilient + Logged + Safe)

## New Features
- Persistent position tracking via JSON
- Daily P&L tracking and lockout after $100 loss
- Trade logging to `trades.csv`
- Error handling around all Alpaca calls
- 5-minute cooldown after each trade exit

## Setup Instructions

1. Install Python: https://www.python.org/downloads/windows/
   - Check "Add Python to PATH" during install

2. Open Command Prompt and install packages:
```
pip install alpaca-trade-api pandas numpy
```

3. Open `config.py` and paste your Alpaca API keys.

4. To run the bot:
   - Open folder
   - Type `cmd` in address bar
   - Run:
```
python run_bot.py
```

Monitor your trades and logs in the `trades.csv` file. All positions are tracked safely.
