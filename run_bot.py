import time
import pytz
import csv
import os
from datetime import datetime, timezone
from blofin_client import get_candles, calculate_indicators
from blofin_client import get_live_usdt_symbols
from signal_engine import generate_signal
from trade_manager import submit_order
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from httplib2 import Http
import json
import io
from google.oauth2.service_account import Credentials

def init_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds_gapi = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_title = f"Signal Log {today_str}"
    sheet = None
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    drive_service = build("drive", "v3", credentials=creds_gapi)

    folder_name = "Leverage Trade Signals"
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    response = drive_service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive', fields='files(id, name)').execute()
    files = response.get('files', [])
    if files:
        folder_id = files[0]['id']
    else:
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')

    try:
        sheet = client.open(sheet_title).sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"📄 Sheet not found. Creating '{sheet_title}'...")
        sheet = client.create(sheet_title).sheet1

    file_id = sheet.spreadsheet.id
    # Move the file into the folder if not already there
    drive_service.files().update(fileId=file_id, addParents=folder_id, removeParents='root', fields='id, parents').execute()

    return sheet

TIMEFRAMES = ["5m", "10m", "15m", "1h"]
SCAN_INTERVAL_SEC = 60 * 5  # run every 5 minutes

def scan():
    print("🔍 Scanning Blofin USDT tokens for leverage setups...\n")
    symbols = get_live_usdt_symbols(min_volume_usdt=5000000)
    print(f"🪙 Found {len(symbols)} tokens to scan\n")
    all_signals = []
    sheet = init_google_sheet()
    earliest_1m_hints = {}

    for symbol in symbols:
        for tf in TIMEFRAMES:
            print(f"🔍 {symbol} @ {tf}")
            df = get_candles(symbol, tf)
            if df is None:
                print(f"⚠️ No data for {symbol} on {tf}")
                continue
            if len(df) < 50:
                print(f"⚠️ Not enough candles for {symbol} on {tf} (got {len(df)})")
                continue

            df = calculate_indicators(df)
            print(f"🧪 Debug: Running signal check on {symbol} @ {tf}")
            print(df.tail(3))  # Show last 3 candles
            print("Latest close:", df['close'].iloc[-1])
            signal = generate_signal(symbol, df, tf)
            is_1m_hint = False
            early_hint_time = None
            signal_delay_minutes = None
            if signal:
                df_1m = get_candles(symbol, "1m")
                if df_1m is not None and len(df_1m) >= 50:
                    df_1m = calculate_indicators(df_1m)
                    signal_1m = generate_signal(symbol, df_1m, "1m")
                    if signal_1m and signal_1m.get("direction") == signal.get("direction"):
                        is_1m_hint = True
                        early_hint_time = df_1m.index[-1]
                        earliest_1m_hints[(symbol, signal_1m.get("direction"))] = early_hint_time
            if signal:
                import pandas as pd
                cst = pytz.timezone("US/Central")
                direction = signal.get("direction")
                early_ts_str = ""
                try:
                    final_ts = df.iloc[-1]["timestamp"]
                    final_ts = pd.to_datetime(final_ts, utc=True)

                    if is_1m_hint and (symbol, direction) in earliest_1m_hints:
                        raw_hint = earliest_1m_hints[(symbol, direction)]
                        if raw_hint and isinstance(raw_hint, (datetime, pd.Timestamp)):
                            if pd.notnull(raw_hint):
                                early_ts = pd.to_datetime(raw_hint, utc=True)
                                early_ts = early_ts.tz_localize('UTC') if early_ts.tzinfo is None else early_ts
                                early_ts_str = early_ts.astimezone(cst).strftime("%Y-%m-%d %H:%M:%S %Z")
                                signal_delay_minutes = round((final_ts - early_ts).total_seconds() / 60.0, 2)
                            else:
                                early_ts_str = ""
                                signal_delay_minutes = ""
                            del earliest_1m_hints[(symbol, direction)]
                        else:
                            early_ts_str = ""
                            signal_delay_minutes = ""
                    else:
                        early_ts_str = ""
                        signal_delay_minutes = ""

                    final_ts_str = final_ts.astimezone(cst).strftime("%Y-%m-%d %H:%M:%S %Z")

                except Exception as e:
                    print(f"⚠️ Timestamp error for {symbol} on {tf}: {e}")
                    signal_delay_minutes = ""
                    final_ts_str = ""
                    early_ts_str = ""

                signal = {
                    "symbol": signal.get("symbol"),
                    "timeframe": signal.get("timeframe"),
                    "type": signal.get("direction"),
                    "price": df['close'].iloc[-1],
                    "rsi": round(df['rsi'].iloc[-1], 2),
                    "ema21": round(df['ema21'].iloc[-1], 6),
                    "ema50": round(df['ema50'].iloc[-1], 6),
                    "score": signal.get("confidence", 0),
                    "price_from_breakout": signal.get("price_from_breakout", ""),
                    "ema_alignment": signal.get("ema_alignment", ""),
                    "signal_age": signal.get("signal_age", 0),
                    "log_type": signal.get("log_type", ""),
                    "notes": [signal.get("reason", "")],
                    "timestamp": final_ts_str,
                    "is_1m_hint": is_1m_hint,
                    "early_hint_time": early_ts_str,
                    "signal_delay_minutes": signal_delay_minutes
                }
                required_keys = ["symbol", "timeframe", "type", "price", "rsi", "ema21", "ema50", "score", "notes"]
                if not all(k in signal for k in required_keys):
                    print(f"⚠️ Signal for {symbol} @ {tf} missing required fields: {signal}")
                    continue

                all_signals.append(signal)
                # Log to Google Sheet only
                if sheet.row_count == 0 or len(sheet.get_all_values()) <= 1:
                    sheet.append_row(["timestamp", "symbol", "timeframe", "type", "price", "rsi", "ema21", "ema50", "score", "price_from_breakout", "ema_alignment", "signal_age", "log_type", "notes", "is_1m_hint", "early_hint_time", "signal_delay_minutes"])
                sheet.append_row([
                    str(signal.get("timestamp", datetime.now(timezone.utc).isoformat())),
                    signal["symbol"],
                    signal["timeframe"],
                    signal["type"],
                    signal["price"],
                    signal["rsi"],
                    signal["ema21"],
                    signal["ema50"],
                    signal["score"],
                    signal.get("price_from_breakout", ""),
                    signal.get("ema_alignment", ""),
                    signal.get("signal_age", ""),
                    signal.get("log_type", ""),
                    ";".join(signal["notes"]),
                    is_1m_hint,
                    early_ts_str,
                    signal.get("signal_delay_minutes", "")
                ])
            else:
                print(f"❌ No signal for {symbol} on {tf}")

    if not all_signals:
        print("❌ No valid setups found.\n")
        return

    # Sort by confidence score (descending)
    all_signals.sort(key=lambda x: x["score"], reverse=True)

    AUTO_TRADE_MIN_SCORE = 4  # Only auto-trade signals with score >= 4

    for sig in all_signals:
        print(f"📈 [{sig['timeframe']}] {sig['symbol']} | {sig['type']} | Score: {sig['score']}")
        print(f"    Price: {sig['price']}, RSI: {sig['rsi']}, EMA21: {sig['ema21']}, EMA50: {sig['ema50']}")
        print(f"    Notes: {', '.join(sig['notes'])}")
        print("-" * 60)
        if sig['score'] >= AUTO_TRADE_MIN_SCORE:
            inst_id = sig['symbol']
            side = "buy" if sig['type'] == "long" else "sell"
            price = str(sig['price'])
            size = "0.1"  # Adjust based on capital or risk model
            print(f"🚀 Auto-submitting trade for {inst_id} ({side}) @ {price}")
            submit_order(inst_id, side, price, size)

def is_bot_enabled():
    return os.environ.get("BOT_DISABLED", "false").lower() != "true"

if __name__ == "__main__":
    if is_bot_enabled():
        try:
            while True:
                scan()
                print("⏳ Waiting for next scan...\n")
                time.sleep(SCAN_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("👋 Scanner stopped.")
    else:
        print("🚫 BOT_DISABLED by environment variable.")