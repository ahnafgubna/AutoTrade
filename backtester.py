import requests
from datetime import datetime, timedelta
from collections import defaultdict

HEADERS = {
    "APCA-API-KEY-ID": "PKUTW6RGEVNSQNAZGKVWBEWPB7",
    "APCA-API-SECRET-KEY": "GxRyVF5Szs8MifJGnVecShpkWwgm6gqjahvoXtY4MMuM",
}

STARTING_CASH = 400
LOOKBACK = 20
Z_SCORE_ENTRY = -1.5    # sweet spot — not too frequent, not too selective
STOP_CANDLES = 2
DAILY_LOSS_LIMIT = 0.03

SYMBOL_CONFIG = {
    "TQQQ": {"stop": 0.008, "target": 0.005, "strategy": "scalp"},
}

TIMEFRAME = "1Min"  # switched from 5Min


def get_historical_bars(symbol, days=30):
    end = datetime.now()
    start = end - timedelta(days=days)
    url = "https://data.alpaca.markets/v2/stocks/bars"
    all_bars = []
    next_token = None

    while True:
        params = {
            "symbols": symbol,
            "timeframe": TIMEFRAME,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "feed": "iex",
            "limit": 10000,
        }
        if next_token:
            params["page_token"] = next_token
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        all_bars.extend(data.get("bars", {}).get(symbol, []))
        next_token = data.get("next_page_token")
        if not next_token:
            break
        print(f"  Fetching page... ({len(all_bars)} bars so far)", end="\r")

    print(f"  Fetched {len(all_bars)} bars total.          ")
    return all_bars


def z_score(prices, lookback):
    if len(prices) < lookback + 1:
        return None
    window = prices[-lookback:]
    mean = sum(window) / lookback
    variance = sum((p - mean) ** 2 for p in window) / lookback
    std = variance ** 0.5
    if std == 0:
        return 0
    return (prices[-1] - mean) / std


def backtest(symbol, days=30):
    cfg = SYMBOL_CONFIG[symbol]
    stop_pct = cfg["stop"]
    target_pct = cfg["target"]
    strategy = cfg["strategy"]

    bars = get_historical_bars(symbol, days=days)
    if not bars:
        print(f"{symbol}: No data available")
        return

    closes = [b["c"] for b in bars]
    timestamps = [b["t"][:10] for b in bars]
    hours = [int(b["t"][11:13]) for b in bars]

    allocated_cash = STARTING_CASH
    cash = allocated_cash
    holding = False
    buy_price = 0
    qty = 0
    candles_below_stop = 0
    trades = []
    wins = 0
    stop_exits = 0
    target_exits = 0
    reversion_exits = 0
    daily_pnl = defaultdict(float)
    daily_loss_limit = STARTING_CASH * DAILY_LOSS_LIMIT
    halted_days = set()

    for i in range(LOOKBACK + 1, len(closes)):
        window = closes[:i]
        price = closes[i]
        date = timestamps[i]
        hour = hours[i]
        z = z_score(window, LOOKBACK)

        if z is None:
            continue

        # Stop entering new trades if daily loss limit hit
        if daily_pnl[date] <= -daily_loss_limit:
            halted_days.add(date)
            if not holding:
                continue



        if holding:
            stop_price = buy_price * (1 - stop_pct)
            target_price = buy_price * (1 + target_pct)

            if price >= target_price:
                holding = False
                cash += price * qty
                pnl = (price - buy_price) * qty
                trades.append(pnl)
                daily_pnl[date] += pnl
                wins += 1
                target_exits += 1
                candles_below_stop = 0
                continue

            if price < stop_price:
                candles_below_stop += 1
                if candles_below_stop >= STOP_CANDLES:
                    holding = False
                    cash += price * qty
                    pnl = (price - buy_price) * qty
                    trades.append(pnl)
                    daily_pnl[date] += pnl
                    if pnl > 0:
                        wins += 1
                    stop_exits += 1
                    candles_below_stop = 0
                continue
            else:
                candles_below_stop = 0

            if strategy == "reversion" and z >= 0:
                holding = False
                cash += price * qty
                pnl = (price - buy_price) * qty
                trades.append(pnl)
                daily_pnl[date] += pnl
                if pnl > 0:
                    wins += 1
                reversion_exits += 1
                continue

        if not holding and z <= Z_SCORE_ENTRY and cash >= price:
            qty = int((cash * 0.8) / price)
            if qty < 1:
                continue
            holding = True
            buy_price = price
            candles_below_stop = 0
            cash -= price * qty

    if holding:
        cash += closes[-1] * qty
        pnl = (closes[-1] - buy_price) * qty
        trades.append(pnl)
        daily_pnl[timestamps[-1]] += pnl
        if pnl > 0:
            wins += 1

    total_return = cash - allocated_cash
    win_rate = (wins / len(trades) * 100) if trades else 0
    avg_trade = sum(trades) / len(trades) if trades else 0
    max_loss = min(trades) if trades else 0

    # Daily stats
    daily_returns = list(daily_pnl.values())
    trading_days = len(daily_returns)
    profitable_days = sum(1 for d in daily_returns if d > 0)
    avg_daily = sum(daily_returns) / trading_days if trading_days else 0
    best_day = max(daily_returns) if daily_returns else 0
    worst_day = min(daily_returns) if daily_returns else 0
    avg_daily_pct = (avg_daily / STARTING_CASH) * 100

    print(f"\n{'='*50}")
    print(f"  {symbol}  |  {strategy}  |  stop: {stop_pct*100}%  target: {target_pct*100}%")
    print(f"{'='*50}")
    print(f"  --- Overall ---")
    print(f"  Trades:           {len(trades)}")
    print(f"  Win rate:         {win_rate:.1f}%")
    print(f"  Avg trade P&L:    ${avg_trade:+.2f}")
    print(f"  Worst trade:      ${max_loss:.2f}")
    print(f"  Target hits:      {target_exits}")
    print(f"  Stop exits:       {stop_exits}")
    print(f"  Total return:     ${total_return:+.2f}")
    print(f"  Final cash:       ${cash:.2f}")
    print(f"  --- Daily Breakdown ---")
    print(f"  Trading days:     {trading_days}")
    print(f"  Profitable days:  {profitable_days} / {trading_days}")
    print(f"  Avg daily P&L:    ${avg_daily:+.2f}  ({avg_daily_pct:+.2f}% of capital)")
    print(f"  Best day:         ${best_day:+.2f}")
    print(f"  Worst day:        ${worst_day:+.2f}")
    print(f"  Halted days:      {len(halted_days)}  (daily loss limit triggered)")
    return total_return


print("Running backtest — TQQQ scalp (365 days, 1-min bars, $400 capital)\n")
for symbol in SYMBOL_CONFIG:
    backtest(symbol, days=365)
print("\nDone.")
