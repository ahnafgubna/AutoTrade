import os
import requests

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
    r = requests.get(f"{DATA_URL}/stocks/bars", headers=HEADERS, params={
        "symbols": symbol, "timeframe": "1Min", "limit": limit, "feed": "iex"
    })
    r.raise_for_status()
    return [b["c"] for b in r.json().get("bars", {}).get(symbol, [])]


def get_position(symbol):
    r = requests.get(f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def place_order(symbol, qty, side):
    r = requests.post(f"{BASE_URL}/orders", headers=HEADERS, json={
        "symbol": symbol, "qty": qty, "side": side,
        "type": "market", "time_in_force": "day"
    })
    r.raise_for_status()
    return r.json()


def close_position(symbol):
    r = requests.delete(f"{BASE_URL}/positions/{symbol}", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()
