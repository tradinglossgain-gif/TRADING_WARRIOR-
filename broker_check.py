"""Read-only sandbox account check / option preview via Webull's official SDK.

No place-order API is called. Only Webull's documented sandbox host is allowed.
"""
import argparse
import json
import logging
import os
import uuid
from datetime import date
from decimal import Decimal


def client_from_env():
    from webull.core.client import ApiClient
    from webull.trade.trade_client import TradeClient
    required = ("WEBULL_APP_KEY", "WEBULL_APP_SECRET")
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError("Configure Webull credentials and the documented sandbox hostname securely")
    host = os.environ.get("WEBULL_SANDBOX_HOST", "api.sandbox.webull.com")
    if host != "api.sandbox.webull.com":
        raise RuntimeError("Only the documented api.sandbox.webull.com endpoint is allowed")
    # The SDK signs locally: a proxy-replacement placeholder cannot be used as a raw signing secret.
    sdk = ApiClient(os.environ["WEBULL_APP_KEY"], os.environ["WEBULL_APP_SECRET"], "us",
                    auto_retry=False, connect_timeout=2, timeout=5)
    sdk.add_endpoint("us", host)
    # Avoid SDK default debug/file logging of signed requests and response bodies.
    sdk.set_stream_logger(log_level=logging.CRITICAL)
    return TradeClient(sdk)


def option_order(direction, strike, expiry, limit_price):
    if direction not in {"CALL", "PUT"}:
        raise ValueError("Choose CALL or PUT")
    strike, limit = Decimal(strike), Decimal(limit_price)
    if not strike.is_finite() or strike <= 0 or not limit.is_finite() or not 0 < limit <= 3:
        raise ValueError("Positive strike and premium limit up to $3.00 required")
    if date.fromisoformat(expiry) < date.today():
        raise ValueError("Expired contract")
    return {"client_order_id": uuid.uuid4().hex, "combo_type": "NORMAL",
            "order_type": "LIMIT", "quantity": "1", "limit_price": str(limit),
            "option_strategy": "SINGLE", "side": "BUY", "time_in_force": "DAY",
            "entrust_type": "QTY", "legs": [{"side": "BUY", "quantity": "1",
                "symbol": "SPY", "strike_price": str(strike), "option_expire_date": expiry,
                "instrument_type": "OPTION", "option_type": direction, "market": "US"}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["accounts", "preview"])
    parser.add_argument("--direction", choices=["CALL", "PUT"])
    parser.add_argument("--strike")
    parser.add_argument("--expiry")
    parser.add_argument("--limit")
    args = parser.parse_args()
    try:
        client = client_from_env()
        if args.operation == "accounts":
            response = client.account_v2.get_account_list()
        else:
            if not all((args.direction, args.strike, args.expiry, args.limit,
                        os.environ.get("WEBULL_ACCOUNT_ID"))):
                raise RuntimeError("Preview requires account ID and explicit contract / premium limit")
            order = option_order(args.direction, args.strike, args.expiry, args.limit)
            response = client.order_v2.preview_option(os.environ["WEBULL_ACCOUNT_ID"], [order])
        if response.status_code != 200:
            raise RuntimeError(f"Webull request failed (HTTP {response.status_code}); inspect securely")
        # Do not dump account details, tokens, or broker response bodies into chat/logs.
        print(json.dumps({"operation": args.operation, "http_status": 200,
                          "note": "HTTP success only; inspect broker business status securely",
                          "order_sent": False}))
    except Exception:
        # SDK exceptions can contain signed URLs / credentials. Do not echo them.
        parser.exit(1, "Sandbox check failed. Verify secure configuration, endpoint, account and API permissions.\n")


if __name__ == "__main__":
    main()
