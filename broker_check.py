"""Read-only sandbox account check / option preview via Webull's official SDK.

No place-order API is called. Only Webull's documented sandbox host is allowed.
"""
import argparse
import json
import logging
import os
import re
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
    # TradeClient initializes authentication in its constructor. Configure its
    # persistent token directory BEFORE creating that client.
    sdk.set_token_dir(os.environ.get("WEBULL_OPENAPI_TOKEN_DIR", ".local/webull-token"))
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


def account_summary(data):
    """Validate the documented account-list response without exposing identifiers."""
    if not isinstance(data, list) or not data:
        raise ValueError("No confirmed accounts returned")
    if any(not isinstance(item, dict) or not isinstance(item.get("account_id"), str)
           or not item["account_id"].strip() for item in data):
        raise ValueError("Unexpected account response")
    return {"account_access_confirmed": True, "account_count": len(data),
            "note": "Account access confirmed on sandbox host; options permissions not yet verified"}


def interactive_preview(client):
    response = client.account_v2.get_account_list()
    if response.status_code != 200:
        raise ValueError("Account lookup failed")
    accounts = response.json()
    account_summary(accounts)
    print("Sandbox accounts (identifiers hidden):")
    for index, account in enumerate(accounts, 1):
        label = str(account.get("account_type", "UNKNOWN"))
        label = label if re.fullmatch(r"[A-Za-z_ -]{1,40}", label) else "UNKNOWN"
        number = str(account.get("account_number", ""))
        suffix = number[-4:] if re.fullmatch(r"[A-Za-z0-9]{4,40}", number) else "unavailable"
        print(f"  {index}: {label}, account number ending {suffix}")
    print("Match the account number to My Account on the Webull sandbox website.")
    print("If the ending is unavailable or does not match, press Ctrl+C; do not guess.")
    selection = int(input("Select the stock/options account number: "))
    if not 1 <= selection <= len(accounts):
        raise ValueError("Invalid selection")
    print("In Webull paper trading, open SPY's option chain and choose an existing contract.")
    direction = input("Option type (CALL or PUT): ").strip().upper()
    expiry = input("Contract expiry (YYYY-MM-DD): ").strip()
    strike = input("Contract strike price: ").strip()
    premium = input("Option premium limit ($0.01 to $3.00, NOT the SPY share price): ").strip()
    order = option_order(direction, strike, expiry, premium)
    print(f"Preview only: 1 SPY {expiry} {strike} {direction}, limit ${premium}. No order will be placed.")
    response = client.order_v2.preview_option(accounts[selection - 1]["account_id"], [order])
    # Report only structure until the preview's business response schema is verified.
    data = response.json()
    fields = sorted(key for key in data if re.fullmatch(r"[a-z_]{1,40}", key)) if isinstance(data, dict) else []
    print(json.dumps({"operation": "option_preview", "http_status": response.status_code,
                      "response_type": type(data).__name__, "response_fields": fields,
                      "error_present": isinstance(data, dict) and bool(data.get("error_code")),
                      "order_sent": False, "options_permissions_confirmed": False,
                      "note": "Preview response requires business-status verification"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["accounts", "preview", "interactive-preview"])
    parser.add_argument("--direction", choices=["CALL", "PUT"])
    parser.add_argument("--strike")
    parser.add_argument("--expiry")
    parser.add_argument("--limit")
    args = parser.parse_args()
    try:
        client = client_from_env()
        if args.operation == "interactive-preview":
            interactive_preview(client)
            return
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
        summary = account_summary(response.json()) if args.operation == "accounts" else {}
        print(json.dumps({"operation": args.operation, "http_status": 200,
                          "note": "HTTP success only; inspect broker business status securely",
                          "order_sent": False, **summary}))
    except Exception:
        # SDK exceptions can contain signed URLs / credentials. Do not echo them.
        parser.exit(1, "Sandbox check failed. Verify secure configuration, endpoint, account and API permissions.\n")


if __name__ == "__main__":
    main()
