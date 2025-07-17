import time
import hmac
import json
import base64
import hashlib
import requests
from uuid import uuid4
from datetime import datetime
from functools import lru_cache

BLOFIN_DEMO_BASE_URL = "https://demo-trading-openapi.blofin.com"
API_KEY = "6b75f32bd01f44aab4a04b43647875ab"
SECRET_KEY = "0040358989dd4fea98071cf7f0da2db8"
PASSPHRASE = "leverage"

@lru_cache()
def fetch_demo_supported_tokens():
    try:
        url = BLOFIN_DEMO_BASE_URL + "/api/v1/market/instruments?instType=SWAP"
        response = requests.get(url)
        data = response.json()
        if data.get("code") == "0":
            return {inst["instId"].upper(): float(inst.get("minSz", 0.001)) for inst in data["data"]}
        else:
            print("⚠️ Failed to fetch supported tokens:", data.get("msg"))
            return {}
    except Exception as e:
        print("⚠️ Error fetching supported tokens:", e)
        return {}

def create_signature(secret_key, method, path, timestamp, nonce, body=None):
    if body:
        body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    else:
        body_str = ""

    prehash = f"{path}{method}{timestamp}{nonce}{body_str}"
    hex_digest = hmac.new(
        secret_key.encode(),
        prehash.encode(),
        hashlib.sha256
    ).hexdigest()
    signature = base64.b64encode(hex_digest.encode()).decode()
    return signature

def is_demo_token(inst_id):
    return inst_id.upper() in fetch_demo_supported_tokens()

def get_order_status(order_id):
    path = f"/api/v1/trade/order/details?ordId={order_id}"
    url = BLOFIN_DEMO_BASE_URL + path
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid4())

    signature = create_signature(SECRET_KEY, method, path, timestamp, nonce)

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-NONCE": nonce,
        "ACCESS-PASSPHRASE": PASSPHRASE
    }

    response = requests.get(url, headers=headers)
    print("📦 Order status response:", response.status_code, response.text)
    return response.json()

def submit_reduce_only_order(inst_id, side, trigger_price, order_type, margin_mode, size, path, url):
    reduce_side = "sell" if side == "buy" else "buy"
    order_data = {
        "instId": inst_id,
        "marginMode": margin_mode,
        "side": reduce_side,
        "orderType": order_type,  # 'stop-market' or 'take-profit-market'
        "triggerPrice": trigger_price,
        "size": str(size),
        "reduceOnly": True
    }
    body = json.dumps(order_data, separators=(',', ':'), ensure_ascii=False)
    ts = str(int(datetime.now().timestamp() * 1000))
    nonce = str(uuid4())
    sig = create_signature(SECRET_KEY, "POST", path, ts, nonce, order_data)
    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": sig,
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-NONCE": nonce,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    r = requests.post(url, headers=headers, data=body)
    print(f"📉 {order_type} order response:", r.status_code, r.text)

def submit_order(inst_id, side, price, size=None, margin_mode="cross", order_type="market", leverage="10"):
    if not is_demo_token(inst_id):
        print(f"🚫 Skipping {inst_id} — not available in demo environment.")
        return {"error": "Token not supported in demo"}

    # Dynamic sizing based on capital and leverage
    capital = 100  # <-- Set your demo capital here (e.g., $100)
    capital_per_trade = capital * 0.20  # 20% of total capital
    notional_value = capital_per_trade * float(leverage)

    token_map = fetch_demo_supported_tokens()
    min_size = token_map.get(inst_id.upper(), 0.001)

    raw_size = notional_value / float(price)
    adjusted_size = max(min_size, raw_size - (raw_size % min_size))
    size = str(round(adjusted_size, 8))

    path = "/api/v1/trade/order"
    url = BLOFIN_DEMO_BASE_URL + path

    order_type = "market"
    order_data = {
        "instId": inst_id,
        "marginMode": margin_mode,
        "side": side,
        "orderType": order_type,
        "size": str(size)
    }
    order_data["orderType"] = order_type

    body_str = json.dumps(order_data, separators=(',', ':'), ensure_ascii=False)
    timestamp = str(int(datetime.now().timestamp() * 1000))
    nonce = str(uuid4())
    signature = create_signature(SECRET_KEY, "POST", path, timestamp, nonce, order_data)

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-NONCE": nonce,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=body_str)
    print("🔁 Order response:", response.status_code, response.text)
    result = response.json()
    print("🔁 Raw response data:", result)
    order_data_resp = result.get("data", [])
    if isinstance(order_data_resp, list) and order_data_resp:
        order_id = order_data_resp[0].get("orderId")
        filled_price_str = order_data_resp[0].get("fillPrice")
        if filled_price_str:
            filled_price = float(filled_price_str)
        else:
            filled_price = float(price)
    else:
        order_id = None
        filled_price = float(price)

    if order_id:
        print(f"⏳ Tracking order ID: {order_id}")
        time.sleep(2)
        status = get_order_status(order_id)
        tp_price = round(filled_price * 1.02, 6)
        sl_price = round(filled_price * 0.98, 6)
        print(f"🎯 Set TP at {tp_price} and ❌ SL at {sl_price}")

        # submit_reduce_only_order(inst_id, side, sl_price, "stop-market", margin_mode, size, path, url)
        # submit_reduce_only_order(inst_id, side, tp_price, "take-profit-market", margin_mode, size, path, url)

        tpsl_path = "/api/v1/trade/order-tpsl"
        tpsl_url = BLOFIN_DEMO_BASE_URL + tpsl_path
        tpsl_data = {
            "instId": inst_id,
            "marginMode": margin_mode,
            "positionSide": "long" if side == "buy" else "short",
            "side": side,
            "tpTriggerPrice": str(tp_price),
            "tpOrderPrice": "-1",  # Market TP
            "slTriggerPrice": str(sl_price),
            "slOrderPrice": "-1",  # Market SL
            "size": str(size),
            "reduceOnly": "true"
        }
        tpsl_body = json.dumps(tpsl_data, separators=(',', ':'), ensure_ascii=False)
        tpsl_timestamp = str(int(datetime.now().timestamp() * 1000))
        tpsl_nonce = str(uuid4())
        tpsl_sig = create_signature(SECRET_KEY, "POST", tpsl_path, tpsl_timestamp, tpsl_nonce, tpsl_data)
        tpsl_headers = {
            "ACCESS-KEY": API_KEY,
            "ACCESS-SIGN": tpsl_sig,
            "ACCESS-TIMESTAMP": tpsl_timestamp,
            "ACCESS-NONCE": tpsl_nonce,
            "ACCESS-PASSPHRASE": PASSPHRASE,
            "Content-Type": "application/json"
        }
        tpsl_resp = requests.post(tpsl_url, headers=tpsl_headers, data=tpsl_body)
        print("🎯 TP/SL order response:", tpsl_resp.status_code, tpsl_resp.text)

        return {
            "order_id": order_id,
            "inst_id": inst_id,
            "side": side,
            "entry_price": filled_price,
            "size": size,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "status": status
        }

    return {"error": result}
