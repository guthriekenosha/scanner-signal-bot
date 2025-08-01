import os
import json
import requests


BLOFIN_API_BASE = "https://openapi.blofin.com/api/v1"

early_hints = {}

def get_top_usdt_symbols(min_volume_usdt=5000000):
    # Step 1: Fetch valid USD perpetual contracts
    instruments_url = f"{BLOFIN_API_BASE}/market/instruments"
    instruments_resp = requests.get(instruments_url)
    instruments_data = instruments_resp.json().get("data", [])

    valid_symbols = set()
    for item in instruments_data:
        if (
            item.get("instType") == "SWAP"
            and item.get("quoteCurrency") == "USDT"
            and item.get("state") == "live"
        ):
            valid_symbols.add(item["instId"])

    # Step 2: Fetch tickers and filter by volume
    tickers_url = f"{BLOFIN_API_BASE}/market/tickers"
    tickers_resp = requests.get(tickers_url)
    tickers_data = tickers_resp.json().get("data", [])

    symbols = []
    for ticker in tickers_data:
        symbol = ticker.get("instId")
        if symbol in valid_symbols:
            try:
                vol_usd = float(ticker.get("volCurrency24h", 0))
                if vol_usd >= min_volume_usdt:
                    symbols.append(symbol)
            except:
                continue

    return symbols


import pandas as pd

def generate_signal(symbol, df, tf):
    """
    Strategy:
    - Long only
    - EMA21 trending up vs 3 candles ago
    - RSI(14) > 45
    - Breakout: close > max(high of previous 2 candles)
    """
    if df is None or len(df) < 10:
        return None

    # Calculate EMA21
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

    # Calculate RSI(14)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bottom bounce logic
    ema_reclaim = df["close"].iloc[-1] > df["ema21"].iloc[-1] and df["close"].iloc[-2] < df["ema21"].iloc[-2]
    rsi_bounce = df["rsi"].iloc[-1] > df["rsi"].iloc[-2] and df["rsi"].iloc[-2] < 30
    recent_bottom = df["low"].iloc[-1] < df["low"].rolling(10).min().iloc[-1] * 1.05
    bounce_score = int(ema_reclaim) + int(rsi_bounce) + int(recent_bottom)
    simulated_pnl = round(((df["close"].iloc[-1] - df["low"].iloc[-1]) / df["low"].iloc[-1]) * 100, 2)

    # Support sweep detection (breakout from lower low)
    recent_support = df["low"].rolling(window=10).min().iloc[-2]
    sweep_occurred = df["low"].iloc[-1] < recent_support * 0.995  # Broke below support
    reclaim_confirmed = df["close"].iloc[-1] > recent_support     # Closed back above it
    rsi_recovery = df["rsi"].iloc[-1] > df["rsi"].iloc[-2] and df["rsi"].iloc[-2] < 35
    bullish_engulfing = df["close"].iloc[-1] > df["open"].iloc[-1] and df["open"].iloc[-1] < df["close"].iloc[-2]
    support_breakout_reversal = sweep_occurred and reclaim_confirmed and (rsi_recovery or bullish_engulfing)

    # Get latest values
    latest = df.iloc[-1]

    # Identify breakout: current close > max high of previous 2 candles (excluding current)
    prev_highs = df["high"].iloc[-3:-1]  # This already captures the 2 prior candles

    # Pre-breakout pressure: price near resistance and increasing volume
    pressure_zone = latest["close"] > prev_highs.max() * 0.98
    volume_building = df["volume"].iloc[-1] > df["volume"].rolling(5).mean().iloc[-2]
    pre_breakout_pressure = pressure_zone and volume_building

    breakout = latest["close"] > prev_highs.max() * 0.995  # Allow breakout trigger if within 0.5% of resistance

    # Confirm EMA trend direction (strictly increasing vs 3 candles ago)
    ema_trend = df["ema21"].iloc[-1] > df["ema21"].iloc[-4]

    # Confirm RSI threshold lowered to 45
    rsi_ok = df["rsi"].iloc[-1] > 45

    # Fast mover flag: candle moves >2.5% in one bar
    fast_candle = (latest["high"] - latest["low"]) / latest["low"] > 0.025

    # Early breakout detection - enhanced with momentum and structure
    proximity_to_resistance = latest["close"] >= prev_highs.max() * 0.98
    rsi_surge = df["rsi"].iloc[-1] - df["rsi"].iloc[-4] > 10
    volume_surge = df["volume"].iloc[-1] > df["volume"].rolling(5).mean().iloc[-2] * 1.5
    structure_build = df["low"].iloc[-2] > df["low"].iloc[-3] and df["low"].iloc[-3] > df["low"].iloc[-4]
    early_breakout = (
        df["ema21"].iloc[-1] > df["ema21"].iloc[-4] and
        df["rsi"].iloc[-1] > 60 and
        (proximity_to_resistance or pre_breakout_pressure) and
        (volume_surge or rsi_surge or structure_build)
    )

    # Optional: Pullback after breakout pattern detection
    has_recent_spike = df["close"].iloc[-2] > df["close"].rolling(10).mean().iloc[-2] * 1.1
    recent_pullback = df["low"].iloc[-1] < df["low"].iloc[-2] and df["close"].iloc[-1] > df["open"].iloc[-1]
    bounce_after_pullback = df["close"].iloc[-1] > df["open"].iloc[-1] and df["close"].iloc[-1] > df["close"].iloc[-2]

    pullback_pattern = has_recent_spike and recent_pullback and bounce_after_pullback

    is_1m_hint = tf == "1m" and proximity_to_resistance and rsi_surge and volume_surge

    # Track early 1m hint appearance
    if is_1m_hint:
        early_hints[symbol] = pd.to_datetime(df.index[-1]).isoformat()
        print(f"⏱️ Stored early hint for {symbol} @ {early_hints[symbol]}")

    if is_1m_hint:
        print(f"🕵️ Hint: {symbol} showing early signal on 1m — Structure + RSI + Volume present.")

    # Print debug snapshot
    print(f"🧪 {symbol} @ {tf} | Close: {latest['close']:.5f} | RSI: {df['rsi'].iloc[-1]:.2f} | EMA trend up: {ema_trend} | Breakout: {breakout}")
    print(f"⚡️ {symbol} @ {tf} | Early breakout setup: {early_breakout} | Proximity: {proximity_to_resistance} | RSI surge: {rsi_surge} | Volume surge: {volume_surge} | Structure: {structure_build}")

    if breakout and ema_trend and rsi_ok:
        momentum_score = 0
        if volume_surge: momentum_score += 1
        if rsi_surge: momentum_score += 1
        if structure_build: momentum_score += 1
        price_from_breakout = (latest["close"] - prev_highs.max()) / prev_highs.max() * 100
        ema_alignment = df["ema21"].iloc[-1] - df["ema21"].iloc[-3]
        signal_strength = min(5, 3 + momentum_score)
        print(f"🔥 {symbol} @ {tf} | Momentum Score: {momentum_score} | Strength: {signal_strength}")
        print(f"🟢 Bottom Bounce Score: {bounce_score} | 🔻 RSI: {rsi_bounce} | 📈 EMA Reclaim: {ema_reclaim} | 📊 Sim PnL: {simulated_pnl}% | 🧠 Stars: {'⭐' * signal_strength}")
        if support_breakout_reversal:
            print(f"🟩 {symbol} @ {tf} | Support Sweep Reversal: ✅ | RSI Reclaim: {rsi_recovery} | Engulfing: {bullish_engulfing}")
        if fast_candle:
            print(f"🚀 {symbol} @ {tf} | FAST MOVER DETECTED! (>2.5% candle)")
        signal_time = pd.to_datetime(df.index[-1], utc=True)
        now = pd.Timestamp.utcnow().replace(tzinfo=pd.Timestamp.utcnow().tzinfo)
        signal_age = round((now - signal_time).total_seconds() / 60.0, 2)
        signal_dict = {
            "symbol": symbol,
            "timeframe": tf,
            "direction": "long",
            "confidence": 4 if not pullback_pattern else 5,
            "reason": "🟢 Confirmation: Breakout + EMA trend + RSI > 45" + (" + Pullback Rebound" if pullback_pattern else ""),
            "signal_age": signal_age,
            "price_from_breakout": round(price_from_breakout, 2),
            "ema_alignment": round(ema_alignment, 5),
            "log_type": "valid",
            "timestamp": str(df.index[-1]),
            "momentum_score": momentum_score,
            "signal_strength": signal_strength,
            "label_type": "confirmation",
            "bottom_bounce_score": bounce_score,
            "rsi_bounce_signal": rsi_bounce,
            "ema_reclaim": ema_reclaim,
            "simulated_bounce_pnl": simulated_pnl,
            "confidence_stars": "⭐" * signal_strength,
            "support_sweep_reversal": support_breakout_reversal,
            "fast_mover": fast_candle,
        }
        if is_1m_hint:
            signal_dict["is_1m_hint"] = True
        if symbol in early_hints and tf != "1m":
            # old code commented out:
            # signal_dict["early_hint_time"] = early_hints[symbol]
            # signal_dict["signal_delay_minutes"] = round(
            #     (df.index[-1] - pd.to_datetime(early_hints[symbol])).total_seconds() / 60, 2
            # )
            # Cleanup after use
            hint_time = pd.to_datetime(early_hints[symbol], errors="coerce")
            if pd.isnull(hint_time):
                print(f"⚠️ Invalid early hint time for {symbol}, skipping signal delay calculation.")
            else:
                signal_dict["early_hint_time"] = early_hints[symbol]
                current_ts = pd.to_datetime(df.index[-1], errors="coerce")
                if pd.isnull(current_ts):
                    print(f"⚠️ Invalid timestamp for {symbol}, skipping delay calc.")
                else:
                    signal_dict["signal_delay_minutes"] = round(
                        (current_ts.replace(tzinfo=None) - hint_time.replace(tzinfo=None)).total_seconds() / 60, 2
                    )
            del early_hints[symbol]
        return signal_dict

    if early_breakout and not breakout:
        momentum_score = 0
        if volume_surge: momentum_score += 1
        if rsi_surge: momentum_score += 1
        if structure_build: momentum_score += 1
        price_from_breakout = (latest["close"] - prev_highs.max()) / prev_highs.max() * 100
        ema_alignment = df["ema21"].iloc[-1] - df["ema21"].iloc[-3]
        signal_strength = min(4, 2 + momentum_score)
        print(f"🔥 {symbol} @ {tf} | Momentum Score: {momentum_score} | Strength: {signal_strength}")
        print(f"🟢 Bottom Bounce Score: {bounce_score} | 🔻 RSI: {rsi_bounce} | 📈 EMA Reclaim: {ema_reclaim} | 📊 Sim PnL: {simulated_pnl}% | 🧠 Stars: {'⭐' * signal_strength}")
        if support_breakout_reversal:
            print(f"🟩 {symbol} @ {tf} | Support Sweep Reversal: ✅ | RSI Reclaim: {rsi_recovery} | Engulfing: {bullish_engulfing}")
        signal_time = pd.to_datetime(df.index[-1], utc=True)
        now = pd.Timestamp.utcnow().replace(tzinfo=pd.Timestamp.utcnow().tzinfo)
        signal_age = round((now - signal_time).total_seconds() / 60.0, 2)
        signal_dict = {
            "symbol": symbol,
            "timeframe": tf,
            "direction": "long",
            "confidence": 3 if not pullback_pattern else 4,
            "reason": "🟦 Anticipation: EMA trend + RSI > 60 + Volume Spike" + (" + Pullback Rebound" if pullback_pattern else ""),
            "signal_age": signal_age,
            "price_from_breakout": round(price_from_breakout, 2),
            "ema_alignment": round(ema_alignment, 5),
            "log_type": "valid",
            "timestamp": str(df.index[-1]),
            "momentum_score": momentum_score,
            "signal_strength": signal_strength,
            "label_type": "anticipation",
            "bottom_bounce_score": bounce_score,
            "rsi_bounce_signal": rsi_bounce,
            "ema_reclaim": ema_reclaim,
            "simulated_bounce_pnl": simulated_pnl,
            "confidence_stars": "⭐" * signal_strength,
            "support_sweep_reversal": support_breakout_reversal,
            "fast_mover": fast_candle,
        }
        if is_1m_hint:
            signal_dict["is_1m_hint"] = True
        if symbol in early_hints and tf != "1m":
            # old code commented out:
            # signal_dict["early_hint_time"] = early_hints[symbol]
            # signal_dict["signal_delay_minutes"] = round(
            #     (df.index[-1] - pd.to_datetime(early_hints[symbol])).total_seconds() / 60, 2
            # )
            # Cleanup after use
            hint_time = pd.to_datetime(early_hints[symbol], errors="coerce")
            if pd.isnull(hint_time):
                print(f"⚠️ Invalid early hint time for {symbol}, skipping signal delay calculation.")
            else:
                signal_dict["early_hint_time"] = early_hints[symbol]
                current_ts = pd.to_datetime(df.index[-1], errors="coerce")
                if pd.isnull(current_ts):
                    print(f"⚠️ Invalid timestamp for {symbol}, skipping delay calc.")
                else:
                    signal_dict["signal_delay_minutes"] = round(
                        (current_ts.replace(tzinfo=None) - hint_time.replace(tzinfo=None)).total_seconds() / 60, 2
                    )
            del early_hints[symbol]
        return signal_dict

    if proximity_to_resistance and (rsi_surge or volume_surge or structure_build):
        print(f"❌ Potential Missed Signal: {symbol} @ {tf} | Structure forming, but breakout not confirmed.")
        if fast_candle:
            print(f"⚠️ {symbol} @ {tf} | Fast mover breakout missed. Consider earlier entry logic.")

    if is_1m_hint:
        return {
            "symbol": symbol,
            "timeframe": tf,
            "direction": "long",
            "confidence": 1,
            "reason": "1m Early Signal Hint: Structure + RSI + Volume",
            "is_1m_hint": True,
            "timestamp": str(df.index[-1]),
            "log_type": "hint",
            "bottom_bounce_score": bounce_score,
            "rsi_bounce_signal": rsi_bounce,
            "ema_reclaim": ema_reclaim,
            "simulated_bounce_pnl": simulated_pnl,
            "confidence_stars": "⭐" * 1,
        }

    return None


# Utility to load skipped signals from disk
def load_skipped_signals(folder_path="Skipped Tokens"):
    skipped = []
    if not os.path.exists(folder_path):
        print(f"📂 Skipped token folder not found: {folder_path}")
        return skipped
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            full_path = os.path.join(folder_path, filename)
            try:
                with open(full_path, "r") as f:
                    data = json.load(f)
                    skipped.append(data)
            except Exception as e:
                print(f"⚠️ Failed to load {filename}: {e}")
    return skipped