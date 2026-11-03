import os
import time
import requests
from datetime import datetime, timedelta, timezone

API_KEY = os.environ["ALPACA_API_KEY"]
API_SECRET = os.environ["ALPACA_API_SECRET"]
BASE_URL = "https://paper-api.alpaca.markets/v2"
DATA_URL = "https://data.alpaca.markets/v2"

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
}


def _request(method, url, **kwargs):
    # Every 5-minute scheduled run gets one shot -- a single dropped
    # connection or transient 5xx from Alpaca used to crash the whole run
    # (and fire a GitHub Actions failure email) even though the next run
    # 5 minutes later would have been fine. Retry those; don't retry 4xx
    # (auth/bad-request errors are real and should surface immediately,
    # not get masked by silently retrying a wrong key).
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.request(method, url, timeout=15, **kwargs)
        except requests.exceptions.RequestException:
            if attempt == max_attempts:
                raise
            time.sleep(1.5 * attempt)
            continue
        if r.status_code >= 500 and attempt < max_attempts:
            time.sleep(1.5 * attempt)
            continue
        return r


def get_account():
    r = _request("GET", f"{BASE_URL}/account", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_bars(symbol, limit=50):
    # Without an explicit `start`, Alpaca anchors to the earliest available
    # bars instead of the most recent ones — the bot was reading data frozen
    # near market open all day. Anchor the window to "now" instead.
    # The window is ~3x wider than `limit` because the free IEX feed skips
    # minutes with no trades on quieter symbols (GLD/TLT), and Alpaca's
    # `limit` truncates from the START of the window — so we fetch the whole
    # window and keep only the most recent `limit` bars ourselves.
    start = (datetime.now(timezone.utc) - timedelta(minutes=limit * 3)).isoformat()
    r = _request("GET", f"{DATA_URL}/stocks/bars", headers=HEADERS, params={
        "symbols": symbol, "timeframe": "1Min", "limit": 10000, "feed": "iex", "start": start
    })
    r.raise_for_status()
    closes = [b["c"] for b in r.json().get("bars", {}).get(symbol, [])]
    return closes[-limit:]


def get_daily_bars(symbol, limit=45):
    # Same anchoring fix as get_bars: fetch a window wider than `limit`
    # trading days (calendar days include weekends/holidays) and keep only
    # the most recent `limit` bars.
    start = (datetime.now(timezone.utc) - timedelta(days=limit * 3)).isoformat()
    r = _request("GET", f"{DATA_URL}/stocks/bars", headers=HEADERS, params={
        "symbols": symbol, "timeframe": "1Day", "limit": 10000, "feed": "iex", "start": start
    })
    r.raise_for_status()
    bars = r.json().get("bars", {}).get(symbol, [])
    return bars[-limit:]


def get_last_fill(symbol, side="buy"):
    r = _request("GET", f"{BASE_URL}/orders", headers=HEADERS, params={
        "status": "closed", "symbols": symbol, "direction": "desc", "limit": 20
    })
    r.raise_for_status()
    for o in r.json():
        if o["side"] == side and o["status"] == "filled" and o.get("filled_at"):
            return datetime.fromisoformat(o["filled_at"].replace("Z", "+00:00"))
    return None


def get_position(symbol):
    r = _request("GET", f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def get_open_orders(symbol):
    r = _request("GET", f"{BASE_URL}/orders", headers=HEADERS, params={
        "status": "open", "symbols": symbol
    })
    r.raise_for_status()
    return r.json()


def place_order(symbol, qty, side):
    # Not retried through _request: a lost response after Alpaca already
    # received the order would cause a retry to submit a second, duplicate
    # order. One attempt only -- a rare failed order just means we skip
    # this cycle's entry, same as if the signal hadn't fired.
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, timeout=15, json={
        "symbol": symbol, "qty": qty, "side": side,
        "type": "market", "time_in_force": "day"
    })
    r.raise_for_status()
    return r.json()


def place_bracket_order(symbol, qty, take_profit_price, stop_price, time_in_force="day"):
    # Whole shares only — Alpaca doesn't support brackets on fractional qty.
    # time_in_force="day" (day-trading bot): unfilled exit legs expire at
    # market close instead of riding into the next session, since positions
    # are force-flattened before close anyway (see main.py).
    # time_in_force="gtc" (swing bot): positions are meant to be held for
    # days, so the exit legs must survive overnight/weekends by design.
    # Not retried -- see place_order's note on duplicate-order risk.
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, timeout=15, json={
        "symbol": symbol, "qty": qty, "side": "buy",
        "type": "market", "time_in_force": time_in_force,
        "order_class": "bracket",
        "take_profit": {"limit_price": take_profit_price},
        "stop_loss": {"stop_price": stop_price},
    })
    r.raise_for_status()
    return r.json()


def get_positions():
    r = _request("GET", f"{BASE_URL}/positions", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def close_position(symbol):
    # Bracket exit legs reserve the position's shares, so Alpaca rejects a
    # close while they're open. Cancel them first.
    for o in get_open_orders(symbol):
        _request("DELETE", f"{BASE_URL}/orders/{o['id']}", headers=HEADERS)
    r = _request("DELETE", f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()
