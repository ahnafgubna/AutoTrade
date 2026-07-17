import os
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

HEADERS = {
    "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
}

STARTING_CASH    = 400
LOOKBACK         = 20
Z_SCORE_ENTRY    = -1.5
STOP_CANDLES     = 2
DAILY_LOSS_LIMIT = 0.03
SLIPPAGE_PCT     = 0.0002  # 0.02% per side (0.04% round-trip) — conservative estimate for liquid ETFs

SYMBOL_CONFIG = {
    "TQQQ": {"stop": 0.008, "target": 0.005, "strategy": "scalp"},
    "SPY":  {"stop": 0.006, "target": 0.004, "strategy": "scalp"},
    "GLD":  {"stop": 0.005, "target": 0.003, "strategy": "scalp"},
    "TLT":  {"stop": 0.005, "target": 0.003, "strategy": "scalp"},
}

TIMEFRAME = "1Min"
ET = timezone(timedelta(hours=-4))


def get_historical_bars(symbol, days=365):
    end   = datetime.now()
    start = end - timedelta(days=days)
    url   = "https://data.alpaca.markets/v2/stocks/bars"
    all_bars, next_token = [], None

    while True:
        params = {
            "symbols": symbol, "timeframe": TIMEFRAME,
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
        print(f"  Fetching... ({len(all_bars)} bars)", end="\r")

    print(f"  {len(all_bars)} bars fetched.          ")
    return all_bars


def z_score(prices, lookback):
    window = prices[-lookback:]
    mean   = sum(window) / lookback
    var    = sum((p - mean) ** 2 for p in window) / lookback
    std    = var ** 0.5
    if std == 0: return 0
    return (prices[-1] - mean) / std


def sma(prices, period):
    return sum(prices[-period:]) / period


def max_drawdown(equity_curve):
    peak, max_dd = equity_curve[0], 0
    for v in equity_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > max_dd: max_dd = dd
    return max_dd


# ── Original Z-Score Scalper ──────────────────────────────────────────────────

def backtest(symbol, days=365):
    if symbol not in SYMBOL_CONFIG:
        print(f"{symbol}: not in SYMBOL_CONFIG"); return
    cfg      = SYMBOL_CONFIG[symbol]
    stop_pct = cfg["stop"]
    tgt_pct  = cfg["target"]

    bars = get_historical_bars(symbol, days)
    if not bars:
        print(f"{symbol}: No data"); return

    closes     = [b["c"] for b in bars]
    timestamps = [b["t"][:10] for b in bars]

    cash = STARTING_CASH
    holding = False
    buy_price = qty = candles_below_stop = 0
    trades, wins = [], 0
    stop_exits = target_exits = 0
    daily_pnl  = defaultdict(float)
    halted_days = set()
    equity_curve = [STARTING_CASH]

    for i in range(LOOKBACK + 1, len(closes)):
        price = closes[i]
        date  = timestamps[i]

        if daily_pnl[date] <= -(STARTING_CASH * DAILY_LOSS_LIMIT):
            halted_days.add(date)
            if not holding: continue

        if holding:
            stop_price = buy_price * (1 - stop_pct)
            tgt_price  = buy_price * (1 + tgt_pct)

            if price >= tgt_price:
                sell_price = price * (1 - SLIPPAGE_PCT)
                cash += sell_price * qty
                pnl = (sell_price - buy_price) * qty
                trades.append(pnl); daily_pnl[date] += pnl
                wins += 1; target_exits += 1
                holding = False; candles_below_stop = 0
                equity_curve.append(cash)
                continue

            if price < stop_price:
                candles_below_stop += 1
                if candles_below_stop >= STOP_CANDLES:
                    sell_price = price * (1 - SLIPPAGE_PCT)
                    cash += sell_price * qty
                    pnl = (sell_price - buy_price) * qty
                    trades.append(pnl); daily_pnl[date] += pnl
                    if pnl > 0: wins += 1
                    stop_exits += 1
                    holding = False; candles_below_stop = 0
                    equity_curve.append(cash)
                continue
            else:
                candles_below_stop = 0

        if not holding:
            if len(closes[:i]) >= LOOKBACK + 1:
                z = z_score(closes[:i], LOOKBACK)
                if z <= Z_SCORE_ENTRY:
                    buy_price = price * (1 + SLIPPAGE_PCT)
                    qty = round((cash * 0.8) / buy_price, 6)
                    if qty >= 0.001:
                        holding = True
                        candles_below_stop = 0; cash -= buy_price * qty

    if holding:
        sell_price = closes[-1] * (1 - SLIPPAGE_PCT)
        pnl = (sell_price - buy_price) * qty
        cash += sell_price * qty
        trades.append(pnl)
        if pnl > 0: wins += 1
        equity_curve.append(cash)

    slippage_cost = len(trades) * 2 * SLIPPAGE_PCT * STARTING_CASH
    _print_results("Z-SCORE SCALPER", symbol, trades, wins, cash,
                   equity_curve, hold_times=None,
                   extra=f"  Target exits:  {target_exits}\n  Stop exits:    {stop_exits}\n  Halted days:   {len(halted_days)}\n  Slippage cost: ~${slippage_cost:.2f} ({SLIPPAGE_PCT*100:.2f}%/side)")


# ── Trend Rider (Trailing Stop) ───────────────────────────────────────────────

def backtest_trend_rider(symbol, days=365):
    SMA_FAST      = 20
    SMA_SLOW      = 50
    TRAIL_STOP    = 0.08   # 8% below peak
    CLOSE_MINUTES = 19 * 60 + 55  # 3:55 PM ET in minutes-since-midnight UTC

    bars = get_historical_bars(symbol, days)
    if not bars:
        print(f"{symbol}: No data"); return

    closes     = [b["c"] for b in bars]
    timestamps = [b["t"][:10] for b in bars]

    # parse bar time as ET minutes since midnight
    def et_minutes(bar):
        dt = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(ET)
        return dt.hour * 60 + dt.minute

    et_mins = [et_minutes(b) for b in bars]

    cash = STARTING_CASH
    holding = False
    buy_price = peak_price = qty = entry_idx = 0
    trades, wins, hold_times = [], 0, []
    daily_pnl   = defaultdict(float)
    halted_days = set()
    equity_curve = [STARTING_CASH]

    for i in range(SMA_SLOW + 1, len(closes)):
        price = closes[i]
        date  = timestamps[i]
        mins  = et_mins[i]

        if daily_pnl[date] <= -(STARTING_CASH * DAILY_LOSS_LIMIT):
            halted_days.add(date)
            if not holding: continue

        if holding:
            if price > peak_price:
                peak_price = price

            # exit conditions
            trail_hit  = price <= peak_price * (1 - TRAIL_STOP)
            eod_exit   = mins >= (15 * 60 + 55)  # 3:55 PM ET

            if trail_hit or eod_exit:
                cash += price * qty
                pnl = (price - buy_price) * qty
                trades.append(pnl); daily_pnl[date] += pnl
                hold_times.append(i - entry_idx)
                if pnl > 0: wins += 1
                holding = False
                equity_curve.append(cash)
                continue

        if not holding:
            if i < SMA_SLOW + 1: continue
            fast = sma(closes[:i], SMA_FAST)
            slow = sma(closes[:i], SMA_SLOW)
            slow_prev = sma(closes[:i-1], SMA_SLOW)

            trend_up   = slow > slow_prev * 1.0001
            above_fast = price > fast

            if trend_up and above_fast:
                qty = round((cash * 0.8) / price, 6)
                if qty >= 0.001:
                    holding = True
                    buy_price = peak_price = price
                    entry_idx = i
                    cash -= price * qty

    if holding:
        pnl = (closes[-1] - buy_price) * qty
        cash += closes[-1] * qty
        trades.append(pnl); hold_times.append(len(closes) - entry_idx)
        if pnl > 0: wins += 1
        equity_curve.append(cash)

    _print_results("TREND RIDER", symbol, trades, wins, cash,
                   equity_curve, hold_times=hold_times,
                   extra=f"  Halted days:   {len(halted_days)}")


# ── Shared print helper ───────────────────────────────────────────────────────

def _print_results(strategy, symbol, trades, wins, cash, equity_curve, hold_times, extra=""):
    total   = cash - STARTING_CASH
    wr      = (wins / len(trades) * 100) if trades else 0
    avg_t   = sum(trades) / len(trades) if trades else 0
    max_t   = min(trades) if trades else 0
    max_dd  = max_drawdown(equity_curve) * 100
    avg_hold = f"{sum(hold_times)/len(hold_times):.1f} min" if hold_times else "n/a"
    days_pnl = []

    print(f"\n{'='*56}")
    print(f"  {strategy} — {symbol}")
    print(f"{'='*56}")
    print(f"  Trades:        {len(trades)}")
    print(f"  Win rate:      {wr:.1f}%")
    print(f"  Avg trade P&L: ${avg_t:+.4f}")
    print(f"  Worst trade:   ${max_t:.2f}")
    print(f"  Total return:  ${total:+.2f}  ({total/STARTING_CASH*100:.1f}%)")
    print(f"  Final cash:    ${cash:.2f}")
    print(f"  Max drawdown:  {max_dd:.1f}%")
    print(f"  Avg hold time: {avg_hold}")
    if extra:
        print(extra)


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    SYMBOLS = ["TQQQ", "SPY", "GLD", "TLT"]

    print("\n" + "="*56)
    print(f"  Z-SCORE SCALPER  (365 days, 1-min, $400/symbol, {SLIPPAGE_PCT*100:.2f}%/side slippage)")
    print("="*56)
    for sym in SYMBOLS:
        print(f"\n{sym}:")
        backtest(sym, days=365)

    print("\n\n" + "="*56)
    print("  TREND RIDER  (365 days, 1-min, $400/symbol)")
    print("="*56)
    for sym in SYMBOLS:
        print(f"\n{sym}:")
        backtest_trend_rider(sym, days=365)

    print("\nDone.")
