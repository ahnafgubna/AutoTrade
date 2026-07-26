"""
Backtests a daily-bar mean reversion swing strategy: no leveraged ETFs,
multi-day holds, targets bigger moves (%) instead of intraday scalps.
Reuses the existing Alpaca market-data credentials -- this doesn't touch
the swing paper account at all, it's pure historical analysis.
"""
import os
import requests
from datetime import datetime, timedelta
from collections import defaultdict

HEADERS = {
    "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
}

STARTING_CASH   = 1000
LOOKBACK_DAYS   = 20     # z-score window, in trading days
Z_SCORE_ENTRY   = -1.5
MAX_HOLD_DAYS   = 10     # force exit if neither target nor stop hit
SLIPPAGE_PCT    = 0.0005 # wider than the scalper's -- less liquid fill timing assumption

# Stop/target are set from ATR (average daily high-low range) instead of a
# fixed %, so the gap widens automatically in volatile stretches and
# tightens in calm ones. Sized once at entry from that day's ATR, not
# re-adjusted daily -- a trailing ATR stop is a further step, not this one.
ATR_PERIOD      = 14
STOP_ATR_MULT   = 2.0
TARGET_ATR_MULT = 2.67   # keeps the ~4:3 reward:risk ratio the fixed-% version used

SYMBOLS = ["SPY", "QQQ"]


def get_daily_bars(symbol, days=1500):
    end   = datetime.now()
    start = end - timedelta(days=days)
    url   = "https://data.alpaca.markets/v2/stocks/bars"
    all_bars, next_token = [], None

    while True:
        params = {
            "symbols": symbol, "timeframe": "1Day",
            "start": start.strftime("%Y-%m-%d"),
            "end":   end.strftime("%Y-%m-%d"),
            "feed": "iex", "limit": 10000,
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

    return all_bars


def compute_atr(highs, lows, closes, period):
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    atr = [None] * len(tr)
    for i in range(period - 1, len(tr)):
        atr[i] = sum(tr[i - period + 1:i + 1]) / period
    return atr


def z_score(prices, lookback):
    window = prices[-lookback:]
    mean   = sum(window) / lookback
    var    = sum((p - mean) ** 2 for p in window) / lookback
    std    = var ** 0.5
    if std == 0: return 0
    return (prices[-1] - mean) / std


def max_drawdown(equity_curve):
    peak, max_dd = equity_curve[0], 0
    for v in equity_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > max_dd: max_dd = dd
    return max_dd


def backtest(symbol, days=1500):
    bars = get_daily_bars(symbol, days)
    if not bars:
        print(f"{symbol}: No data"); return
    if len(bars) < LOOKBACK_DAYS + 10:
        print(f"{symbol}: Only {len(bars)} daily bars available -- not enough history"); return

    closes     = [b["c"] for b in bars]
    highs      = [b["h"] for b in bars]
    lows       = [b["l"] for b in bars]
    dates      = [b["t"][:10] for b in bars]
    atr        = compute_atr(highs, lows, closes, ATR_PERIOD)

    start_idx = max(LOOKBACK_DAYS + 1, ATR_PERIOD)

    cash = STARTING_CASH
    holding = False
    buy_price = qty = entry_idx = 0
    target_pr = stop_pr = 0
    trades, wins, hold_days_list = [], 0, []
    stop_pct_list = []
    target_exits = stop_exits = timeout_exits = 0
    equity_curve = [STARTING_CASH]

    for i in range(start_idx, len(closes)):
        price = closes[i]

        if holding:
            days_held = i - entry_idx

            exit_reason = None
            if price >= target_pr:
                exit_reason = "target"
            elif price <= stop_pr:
                exit_reason = "stop"
            elif days_held >= MAX_HOLD_DAYS:
                exit_reason = "timeout"

            if exit_reason:
                sell_price = price * (1 - SLIPPAGE_PCT)
                pnl = (sell_price - buy_price) * qty
                cash += sell_price * qty
                trades.append(pnl); hold_days_list.append(days_held)
                if pnl > 0: wins += 1
                if exit_reason == "target": target_exits += 1
                elif exit_reason == "stop": stop_exits += 1
                else: timeout_exits += 1
                holding = False
                equity_curve.append(cash)
                continue

        if not holding and atr[i] is not None:
            z = z_score(closes[:i+1], LOOKBACK_DAYS)
            if z <= Z_SCORE_ENTRY:
                buy_price = price * (1 + SLIPPAGE_PCT)
                qty = round((cash * 0.9) / buy_price, 4)
                if qty > 0:
                    holding = True
                    entry_idx = i
                    cash -= buy_price * qty
                    stop_pr   = buy_price - atr[i] * STOP_ATR_MULT
                    target_pr = buy_price + atr[i] * TARGET_ATR_MULT
                    stop_pct_list.append((buy_price - stop_pr) / buy_price * 100)

    if holding:
        sell_price = closes[-1] * (1 - SLIPPAGE_PCT)
        pnl = (sell_price - buy_price) * qty
        cash += sell_price * qty
        trades.append(pnl); hold_days_list.append(len(closes) - 1 - entry_idx)
        if pnl > 0: wins += 1
        equity_curve.append(cash)

    total  = cash - STARTING_CASH
    wr     = (wins / len(trades) * 100) if trades else 0
    avg_t  = sum(trades) / len(trades) if trades else 0
    worst  = min(trades) if trades else 0
    best   = max(trades) if trades else 0
    max_dd = max_drawdown(equity_curve) * 100
    avg_hold = sum(hold_days_list) / len(hold_days_list) if hold_days_list else 0
    avg_stop_pct = sum(stop_pct_list) / len(stop_pct_list) if stop_pct_list else 0
    min_stop_pct = min(stop_pct_list) if stop_pct_list else 0
    max_stop_pct = max(stop_pct_list) if stop_pct_list else 0

    print(f"\n{'='*56}")
    print(f"  SWING MEAN REVERSION (ATR stops) — {symbol}  ({dates[0]} to {dates[-1]}, {len(bars)} daily bars)")
    print(f"{'='*56}")
    print(f"  Trades:        {len(trades)}")
    print(f"  Win rate:      {wr:.1f}%")
    print(f"  Avg trade P&L: ${avg_t:+.2f}")
    print(f"  Best trade:    ${best:+.2f}")
    print(f"  Worst trade:   ${worst:+.2f}")
    print(f"  Total return:  ${total:+.2f}  ({total/STARTING_CASH*100:.1f}%)")
    print(f"  Max drawdown:  {max_dd:.1f}%")
    print(f"  Avg hold time: {avg_hold:.1f} days")
    print(f"  Implied stop:  {avg_stop_pct:.2f}% avg  (range {min_stop_pct:.2f}%–{max_stop_pct:.2f}%)")
    print(f"  Target exits:  {target_exits}  | Stop exits: {stop_exits}  | Timeout exits: {timeout_exits}")


if __name__ == "__main__":
    print("="*56)
    print(f"  SWING BACKTEST — z<={Z_SCORE_ENTRY}, stop={STOP_ATR_MULT}x ATR({ATR_PERIOD}), target={TARGET_ATR_MULT}x ATR, max hold={MAX_HOLD_DAYS}d")
    print("="*56)
    for sym in SYMBOLS:
        backtest(sym)
    print("\nDone.")
