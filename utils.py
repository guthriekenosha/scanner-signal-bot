import os
import requests

from dotenv import load_dotenv
load_dotenv()

import os
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(signal):
    """
    Sends a formatted Telegram alert using environment variables:
    TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set.
    """
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ Telegram credentials not set.")
        return

    text = f"""
📈 {signal['symbol']} @ {signal['timeframe']}
{signal['reason']}
Confidence: {signal['confidence_stars']}
Price from BO: {signal.get('price_from_breakout', '?')}%
EMA Align: {signal.get('ema_alignment', '?')}
Momentum: {signal.get('momentum_score', '?')}
🕒 Signal Age: {signal.get('signal_age', '?')} min
📌 {signal['log_type'].capitalize()} Signal
"""

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text.strip()
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"❌ Failed to send Telegram alert: {response.text}")
    except Exception as e:
        print(f"❌ Telegram alert exception: {e}")
        
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

def load_skipped_signals():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_title = f"Skipped {today_str}"

    try:
        sheet = client.open(sheet_title).sheet1
        records = sheet.get_all_records()
        return [{"symbol": row["symbol"], "timeframe": row["timeframe"]} for row in records if "symbol" in row and "timeframe" in row]
    except Exception as e:
        print(f"⚠️ Error loading skipped signals: {e}")
        return []