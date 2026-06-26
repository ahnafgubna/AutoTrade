"""
Single-execution trading script — designed to be called every 5 minutes
by GitHub Actions. State (position, entry price) is read from Alpaca API
each run rather than stored in memory.
"""
import os
import sys
from broker import get_account, get_bars, get_position, place_order, close_position
from strategy import should_enter, should_exit, LOOKBACK

SYMBOL = "TQQQ"
POSITION_PCT = 0.80
DAILY_LOSS_LIMIT_PCT = 0.03


def run():
    account = get_account()
    cash = float(account["buying_power"])
    equity = float(account["equity"])
    last_equity = float(account.get("last_equity", equity))
    day_pnl = equity - last_equity

    print(f"Account | Equity: ${equity:.2f} | Day P&L: ${day_pnl:+.2f} | Cash: ${cash:.2f}")

    # Daily loss limit check
    if day_pnl <= -(last_equity * DAILY_LOSS_LIMIT_PCT):
        print(f"Daily loss limit hit (${day_pnl:.2f}). No trades today.")
        sys.exit(0)

    # Get price data
    prices = get_bars(SYMBOL, limit=LOOKBACK + 5)
    if len(prices) < LOOKBACK + 1:
        print("Not enough price data yet. Exiting.")
        sys.exit(0)

    price = prices[-1]
    position = get_position(SYMBOL)

    if position:
        qty = int(float(position["qty"]))
        buy_price = float(position["avg_entry_price"])
        candles_below_stop = 0  # stateless — rely on stop/target check only

        action, _ = should_exit(price, buy_price, candles_below_stop)

        if action == "take_profit":
            close_position(SYMBOL)
            pnl = (price - buy_price) * qty
            print(f"TAKE PROFIT | Sold {qty} {SYMBOL} @ ${price:.2f} | P&L: ${pnl:+.2f}")

        elif action == "stop_loss":
            close_position(SYMBOL)
            pnl = (price - buy_price) * qty
            print(f"STOP LOSS | Sold {qty} {SYMBOL} @ ${price:.2f} | P&L: ${pnl:+.2f}")

        else:
            unrealized = (price - buy_price) * qty
            print(f"Holding {qty} {SYMBOL} | Entry: ${buy_price:.2f} | Now: ${price:.2f} | Unrealized: ${unrealized:+.2f}")

    else:
        if should_enter(prices):
            qty = int((cash * POSITION_PCT) / price)
            if qty >= 1:
                place_order(SYMBOL, qty, "buy")
                print(f"BUY | {qty} {SYMBOL} @ ${price:.2f} | Total: ${qty * price:.2f}")
            else:
                print(f"Signal triggered but insufficient cash (${cash:.2f})")
        else:
            print(f"No entry signal | {SYMBOL} @ ${price:.2f}")


if __name__ == "__main__":
    run()
