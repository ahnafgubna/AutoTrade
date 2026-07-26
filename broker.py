import os
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


def get_account():
    r = requests.get(f"{BASE_URL}/account", headers=HEADERS)
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
    r = requests.get(f"{DATA_URL}/stocks/bars", headers=HEADERS, params={
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
    r = requests.get(f"{DATA_URL}/stocks/bars", headers=HEADERS, params={
        "symbols": symbol, "timeframe": "1Day", "limit": 10000, "feed": "iex", "start": start
    })
    r.raise_for_status()
    bars = r.json().get("bars", {}).get(symbol, [])
    return bars[-limit:]


def get_last_fill(symbol, side="buy"):
    r = requests.get(f"{BASE_URL}/orders", headers=HEADERS, params={
        "status": "closed", "symbols": symbol, "direction": "desc", "limit": 20
    })
    r.raise_for_status()
    for o in r.json():
        if o["side"] == side and o["status"] == "filled" and o.get("filled_at"):
            return datetime.fromisoformat(o["filled_at"].replace("Z", "+00:00"))
    return None


def get_position(symbol):
    r = requests.get(f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def get_open_orders(symbol):
    r = requests.get(f"{BASE_URL}/orders", headers=HEADERS, params={
        "status": "open", "symbols": symbol
    })
    r.raise_for_status()
    return r.json()


def place_order(symbol, qty, side):
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, json={
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
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, json={
        "symbol": symbol, "qty": qty, "side": "buy",
        "type": "market", "time_in_force": time_in_force,
        "order_class": "bracket",
        "take_profit": {"limit_price": take_profit_price},
        "stop_loss": {"stop_price": stop_price},
    })
    r.raise_for_status()
    return r.json()


def close_position(symbol):
    r = requests.delete(f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()
