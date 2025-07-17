# blofin_client.py
import requests
import pandas as pd
from datetime import datetime
import time

import random

def retry_get(url, retries=3, base_delay=2, backoff=2):
    import random
    delay = base_delay
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", delay))
                print(f"🛑 Rate limited. Waiting {retry_after} seconds (attempt {attempt + 1}/{retries})...")
                time.sleep(retry_after)
            else:
                print(f"⚠️ HTTP Error {resp.status_code}: {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"🚫 Connection refused or failed: {e}")
        except requests.RequestException as e:
            print(f"⏳ Retry {attempt + 1} for {url} due to {e}")
        
        wait = delay + random.uniform(0.5, 1.5)
        print(f"⏲️ Waiting {round(wait, 2)}s before next attempt...")
        time.sleep(wait)
        delay *= backoff

    raise Exception(f"❌ Failed to fetch {url} after {retries} retries.")

BLOFIN_API_BASE = "https://openapi.blofin.com/api/v1"

def get_top_usdt_symbols(min_volume_usdt=50000000):
    url = f"{BLOFIN_API_BASE}/market/tickers"
    resp = retry_get(url)
    data = resp.json().get("data", [])

    symbols = []
    for item in data:
        if not item["instId"].endswith("USD"):
            continue
        try:
            vol = float(item.get("volCurrency24h", 0))
            if vol >= min_volume_usdt:
                symbols.append(item["instId"])
        except:
            continue
    return symbols

def get_candles(symbol: str, interval: str = "15m", limit: int = 150):
    interval_map = {
        "1m": "1m", "3m": "3m", "5m": "5m", "10m": "10m", "15m": "15m", "30m": "30m",
        "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "8h": "8H", "12h": "12H",
        "1d": "1D", "3d": "3D", "1w": "1W", "1mo": "1M"
    }
    granularity = interval_map.get(interval.lower(), "15m")
    url = f"{BLOFIN_API_BASE}/market/candles?instId={symbol}&bar={granularity}&limit={limit}"
    resp = retry_get(url)
    if resp.status_code != 200:
        print(f"⚠️ Failed to fetch candles for {symbol}: HTTP {resp.status_code}")
        return None
    try:
        candles = resp.json().get("data", [])
    except Exception as e:
        print(f"⚠️ Error parsing JSON for {symbol}: {e}")
        return None
    if not candles:
        print(f"⚠️ No candles returned for {symbol}")
        return None

    df = pd.DataFrame(candles, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "volCurrency", "volQuote", "confirm"
    ])
    df = df.iloc[::-1]  # newest last
    df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df

def calculate_indicators(df: pd.DataFrame):
    df["ema21"] = df["close"].ewm(span=21).mean()
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["rsi"] = compute_rsi(df["close"])
    df["atr"] = compute_atr(df)
    return df

def compute_rsi(series: pd.Series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / (avg_loss + 1e-6)
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def get_live_usdt_symbols(min_volume_usdt=5000000):
    url = "https://openapi.blofin.com/api/v1/market/tickers"
    response = retry_get(url)
    data = response.json()

    symbols = []
    for item in data.get("data", []):
        symbol = item.get("instId", "")
        if not symbol.endswith("-USDT"):
            continue
        try:
            volume = float(item.get("volCurrency24h", 0))
            if volume >= min_volume_usdt:
                symbols.append(symbol)
        except Exception as e:
            pass

    return symbols