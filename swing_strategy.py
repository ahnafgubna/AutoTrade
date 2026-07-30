"""
Same signal validated in swing_backtester.py: daily-bar z-score mean
reversion with ATR-sized stop/target. Kept in one place so the live bot
and the backtester can't quietly drift apart.
"""

SYMBOLS         = ["SPY", "QQQ"]
LOOKBACK_DAYS   = 20
Z_SCORE_ENTRY   = -1.5
ATR_PERIOD      = 14
STOP_ATR_MULT   = 2.0
TARGET_ATR_MULT = 2.67
MAX_HOLD_DAYS   = 10

# Position size is derived from the stop distance so a stop-hit always
# costs about the same % of the account, instead of every trade committing
# a flat share of capital regardless of how wide the ATR stop is.
RISK_PCT         = 0.02
MAX_POSITION_PCT = 0.90  # cash ceiling -- no margin available


def z_score(prices, lookback):
    window = prices[-lookback:]
    mean   = sum(window) / lookback
    var    = sum((p - mean) ** 2 for p in window) / lookback
    std    = var ** 0.5
    if std == 0: return 0
    return (prices[-1] - mean) / std


def atr(highs, lows, closes, period):
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    if len(tr) < period:
        return None
    return sum(tr[-period:]) / period


def should_enter(closes):
    if len(closes) < LOOKBACK_DAYS + 1:
        return False
    return z_score(closes, LOOKBACK_DAYS) <= Z_SCORE_ENTRY


def stop_target_prices(entry_price, atr_value):
    stop_price   = entry_price - atr_value * STOP_ATR_MULT
    target_price = entry_price + atr_value * TARGET_ATR_MULT
    return round(stop_price, 2), round(target_price, 2)


def position_size(cash, entry_price, stop_price):
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        return 0
    risk_qty = (cash * RISK_PCT) / stop_distance
    max_qty  = (cash * MAX_POSITION_PCT) / entry_price
    return int(min(risk_qty, max_qty))  # whole shares -- brackets don't support fractional
