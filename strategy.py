LOOKBACK = 20
Z_SCORE_ENTRY = -1.5
TAKE_PROFIT_PCT = 0.005   # 0.5%
STOP_LOSS_PCT = 0.008     # 0.8%
STOP_CANDLES = 2          # price must stay below stop for 2 candles before exiting


def z_score(prices):
    if len(prices) < LOOKBACK + 1:
        return None
    window = prices[-LOOKBACK:]
    mean = sum(window) / LOOKBACK
    variance = sum((p - mean) ** 2 for p in window) / LOOKBACK
    std = variance ** 0.5
    if std == 0:
        return 0
    return (prices[-1] - mean) / std


def should_enter(prices):
    """Return True if z-score signals a mean reversion buy."""
    z = z_score(prices)
    return z is not None and z <= Z_SCORE_ENTRY


def should_exit(current_price, buy_price, candles_below_stop):
    """
    Returns ('take_profit' | 'stop_loss' | 'hold'), updated candles_below_stop count.
    """
    target = buy_price * (1 + TAKE_PROFIT_PCT)
    stop = buy_price * (1 - STOP_LOSS_PCT)

    if current_price >= target:
        return "take_profit", 0

    if current_price < stop:
        candles_below_stop += 1
        if candles_below_stop >= STOP_CANDLES:
            return "stop_loss", 0
        return "hold", candles_below_stop
    else:
        return "hold", 0  # recovered above stop, reset counter
