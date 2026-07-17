"""
Single-execution trading script — called every 5 minutes by GitHub Actions.
Loops through all symbols in SYMBOL_CONFIG, checks signals, manages positions.
State is read from Alpaca each run (stateless design).
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from broker import (get_account, get_bars, get_position, get_open_orders,
                    place_bracket_order, close_position)
from strategy import should_enter, LOOKBACK

# Stops are ~25% wider than the backtested values: exits now fire instantly
# server-side (bracket orders) instead of waiting for 2 confirmed candles,
# so a tighter stop would get picked off by single-tick noise.
SYMBOL_CONFIG = {
    "TQQQ": {"z_entry": -1.5, "take_profit": 0.005, "stop_loss": 0.010},
    "SPY":  {"z_entry": -1.5, "take_profit": 0.004, "stop_loss": 0.0075},
    "TLT":  {"z_entry": -1.2, "take_profit": 0.003, "stop_loss": 0.006},
    "GLD":  {"z_entry": -1.2, "take_profit": 0.003, "stop_loss": 0.006},
}

POSITION_PCT         = 0.80
DAILY_LOSS_LIMIT_PCT = 0.03

ET = timezone(timedelta(hours=-4))
MARKET_OPEN  = 9 * 60 + 30
MARKET_CLOSE = 16 * 60


def run():
    now_et  = datetime.now(ET)
    minutes = now_et.hour * 60 + now_et.minute

    if not (MARKET_OPEN <= minutes < MARKET_CLOSE):
        print(f"Outside market hours ({now_et.strftime('%I:%M %p')} ET). Exiting.")
        sys.exit(0)

    account     = get_account()
    equity      = float(account["equity"])
    last_equity = float(account.get("last_equity", equity))  # Alpaca provides this
    day_pnl     = equity - last_equity

    print(f"Account | Equity: ${equity:.2f} | Day P&L: ${day_pnl:+.2f}")

    if day_pnl <= -(last_equity * DAILY_LOSS_LIMIT_PCT):
        print(f"Daily loss limit hit (${day_pnl:.2f}). No new trades today.")
        sys.exit(0)

    # Use the full paper account, split evenly across all symbols
    capital_per_symbol = equity / len(SYMBOL_CONFIG)

    for symbol, cfg in SYMBOL_CONFIG.items():
        print(f"\n── {symbol} ──")

        prices = get_bars(symbol, limit=LOOKBACK + 5)
        if len(prices) < LOOKBACK + 1:
            print(f"  Not enough data, skipping.")
            continue

        price    = prices[-1]
        position = get_position(symbol)

        if position:
            qty        = float(position["qty"])
            buy_price  = float(position["avg_entry_price"])
            unrealized = (price - buy_price) * qty

            if get_open_orders(symbol):
                # Exit legs live on Alpaca's servers (bracket order) — they
                # fire in real time, no action needed here.
                print(f"  Holding {qty} | Entry: ${buy_price:.2f} | Now: ${price:.2f} | Unrealized: ${unrealized:+.2f} | bracket active")
            else:
                # Legacy position with no bracket protection — manage manually.
                target_price = buy_price * (1 + cfg["take_profit"])
                stop_price   = buy_price * (1 - cfg["stop_loss"])
                if price >= target_price or price <= stop_price:
                    close_position(symbol)
                    print(f"  MANUAL EXIT | Sold {qty} @ ~${price:.2f} | P&L: ${unrealized:+.2f}")
                else:
                    print(f"  Holding {qty} (no bracket) | Entry: ${buy_price:.2f} | Now: ${price:.2f} | Unrealized: ${unrealized:+.2f}")

        else:
            if should_enter(prices, z_entry=cfg["z_entry"]):
                cash_to_use = capital_per_symbol * POSITION_PCT
                qty = int(cash_to_use / price)  # whole shares — brackets don't support fractional

                if qty >= 1:
                    tp = round(price * (1 + cfg["take_profit"]), 2)
                    sl = round(price * (1 - cfg["stop_loss"]), 2)
                    place_bracket_order(symbol, qty, tp, sl)
                    print(f"  BUY {qty} @ ~${price:.2f} | TP ${tp:.2f} / SL ${sl:.2f} | Total: ~${qty * price:.2f}")
                else:
                    print(f"  Signal triggered but allocation too small for 1 share.")
            else:
                print(f"  No entry signal @ ${price:.2f}")


if __name__ == "__main__":
    run()
