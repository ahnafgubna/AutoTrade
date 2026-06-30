"""
Single-execution trading script — called every 5 minutes by GitHub Actions.
Loops through all symbols in SYMBOL_CONFIG, checks signals, manages positions.
State is read from Alpaca each run (stateless design).
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from broker import get_account, get_bars, get_position, place_order, close_position
from strategy import should_enter, LOOKBACK

SYMBOL_CONFIG = {
    "TQQQ": {"z_entry": -1.5, "take_profit": 0.005, "stop_loss": 0.008},
    "SPY":  {"z_entry": -1.5, "take_profit": 0.004, "stop_loss": 0.006},
    "QQQ":  {"z_entry": -1.5, "take_profit": 0.004, "stop_loss": 0.007},
    "NVDA": {"z_entry": -1.5, "take_profit": 0.005, "stop_loss": 0.008},
}

POSITION_PCT         = 0.80
CAPITAL_PER_SYMBOL   = 400
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

    for symbol, cfg in SYMBOL_CONFIG.items():
        print(f"\n── {symbol} ──")

        prices = get_bars(symbol, limit=LOOKBACK + 5)
        if len(prices) < LOOKBACK + 1:
            print(f"  Not enough data, skipping.")
            continue

        price    = prices[-1]
        position = get_position(symbol)

        if position:
            qty       = float(position["qty"])
            buy_price = float(position["avg_entry_price"])

            target_price = buy_price * (1 + cfg["take_profit"])
            stop_price   = buy_price * (1 - cfg["stop_loss"])

            if price >= target_price:
                close_position(symbol)
                pnl = (price - buy_price) * qty
                print(f"  TAKE PROFIT | Sold {qty} @ ${price:.2f} | P&L: ${pnl:+.2f}")

            elif price < stop_price:
                close_position(symbol)
                pnl = (price - buy_price) * qty
                print(f"  STOP LOSS   | Sold {qty} @ ${price:.2f} | P&L: ${pnl:+.2f}")

            else:
                unrealized = (price - buy_price) * qty
                print(f"  Holding {qty} | Entry: ${buy_price:.2f} | Now: ${price:.2f} | Unrealized: ${unrealized:+.2f}")

        else:
            if should_enter(prices, z_entry=cfg["z_entry"]):
                cash_to_use = CAPITAL_PER_SYMBOL * POSITION_PCT
                qty = round(cash_to_use / price, 6)  # fractional shares fix

                if qty >= 0.001:
                    place_order(symbol, qty, "buy")
                    print(f"  BUY {qty} @ ${price:.2f} | Total: ${qty * price:.2f}")
                else:
                    print(f"  Signal triggered but allocation too small.")
            else:
                print(f"  No entry signal @ ${price:.2f}")


if __name__ == "__main__":
    run()
