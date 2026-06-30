LOOKBACK = 20
STOP_CANDLES = 2

# Default params (used if no per-symbol override passed)
Z_SCORE_ENTRY   = -1.5
TAKE_PROFIT_PCT = 0.005
STOP_LOSS_PCT   = 0.008


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


def should_enter(prices, z_entry=Z_SCORE_ENTRY):
    z = z_score(prices)
    return z is not None and z <= z_entry


def should_exit(current_price, buy_price, candles_below_stop,
                take_profit=TAKE_PROFIT_PCT, stop_loss=STOP_LOSS_PCT):
    target = buy_price * (1 + take_profit)
    stop   = buy_price * (1 - stop_loss)

    if current_price >= target:
        return "take_profit", 0

    if current_price < stop:
        candles_below_stop += 1
        if candles_below_stop >= STOP_CANDLES:
            return "stop_loss", 0
        return "hold", candles_below_stop

    return "hold", 0
