"""
Single-execution swing trading script — runs once per day (near market
close), not every 5 minutes. The signal is computed on daily bars, so
running more often would just react to the day's still-forming bar and
risk flipping in and out of the z-score threshold intraday.

Exits are handled by Alpaca bracket orders (target/stop) firing in real
time on their servers; this script only needs to place new entries and
force-close anything that's timed out without hitting either.

Positions are meant to be held for multiple days -- unlike the day
trading bot, holding through overnight/weekend gaps is the point here,
not a bug to guard against.
"""
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from broker import (get_account, get_daily_bars, get_position, get_last_fill,
                     place_bracket_order, close_position)
from swing_strategy import (SYMBOLS, LOOKBACK_DAYS, ATR_PERIOD, MAX_HOLD_DAYS,
                             should_enter, atr, stop_target_prices, position_size)

ET = ZoneInfo("America/New_York")  # handles EDT/EST switch automatically
MARKET_OPEN  = 9 * 60 + 30
MARKET_CLOSE = 16 * 60


def business_days_between(start, end):
    days, cur = 0, start
    while cur.date() < end.date():
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def run():
    now_et  = datetime.now(ET)
    minutes = now_et.hour * 60 + now_et.minute

    if not (MARKET_OPEN <= minutes < MARKET_CLOSE):
        print(f"Outside market hours ({now_et.strftime('%I:%M %p')} ET). Exiting.")
        sys.exit(0)

    account = get_account()
    equity  = float(account["equity"])
    print(f"Account | Equity: ${equity:.2f}")

    capital_per_symbol = equity / len(SYMBOLS)
    needed_bars = max(LOOKBACK_DAYS, ATR_PERIOD) + 1

    for symbol in SYMBOLS:
        print(f"\n── {symbol} ──")

        bars = get_daily_bars(symbol, limit=needed_bars + 10)
        if len(bars) < needed_bars:
            print(f"  Not enough daily bars ({len(bars)}), skipping.")
            continue

        closes = [b["c"] for b in bars]
        highs  = [b["h"] for b in bars]
        lows   = [b["l"] for b in bars]
        price  = closes[-1]

        position = get_position(symbol)

        if position:
            qty        = float(position["qty"])
            buy_price  = float(position["avg_entry_price"])
            unrealized = (price - buy_price) * qty

            entry_fill = get_last_fill(symbol, side="buy")
            days_held  = business_days_between(entry_fill, now_et) if entry_fill else 0

            if days_held >= MAX_HOLD_DAYS:
                close_position(symbol)
                print(f"  TIMEOUT EXIT | Sold {qty} @ ~${price:.2f} | Held {days_held}d | Unrealized: ${unrealized:+.2f}")
            else:
                print(f"  Holding {qty} | Entry: ${buy_price:.2f} | Now: ${price:.2f} | Held {days_held}d | Unrealized: ${unrealized:+.2f} | bracket active")

        else:
            if should_enter(closes):
                atr_value = atr(highs, lows, closes, ATR_PERIOD)
                if atr_value:
                    stop_pr, target_pr = stop_target_prices(price, atr_value)
                    qty = position_size(capital_per_symbol, price, stop_pr)

                    if qty >= 1:
                        place_bracket_order(symbol, qty, target_pr, stop_pr, time_in_force="gtc")
                        risk_dollars = qty * (price - stop_pr)
                        print(f"  BUY {qty} @ ~${price:.2f} | TP ${target_pr:.2f} / SL ${stop_pr:.2f} | Risking ~${risk_dollars:.2f} | Total: ~${qty * price:.2f}")
                    else:
                        print(f"  Signal triggered but allocation too small for 1 share.")
            else:
                print(f"  No entry signal @ ${price:.2f}")


if __name__ == "__main__":
    run()
