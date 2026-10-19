"""Durable, sandbox-only SPY 0DTE execution. One worker/process only."""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from broker_check import account_summary, client_from_env

TERMINAL = ("CLOSED", "SKIPPED")
NY = ZoneInfo("America/New_York")


class BrokerError(RuntimeError):
    """Only constant, non-sensitive messages may be raised with this type."""


def response_data(response):
    if response.status_code != 200:
        raise BrokerError("BROKER_HTTP_ERROR")
    data = response.json()
    if isinstance(data, dict) and data.get("error_code"):
        raise BrokerError("BROKER_BUSINESS_ERROR")
    return data


def atm_contract(payload, now):
    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    if timestamp.astimezone(NY).date() != now.astimezone(NY).date():
        raise BrokerError("ENTRY_NOT_TODAY")
    direction = payload["direction"]
    if direction not in {"CALL", "PUT"}:
        raise BrokerError("INVALID_DIRECTION")
    strike = Decimal(str(payload["entry"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    expiry = now.astimezone(NY).date()
    symbol = f"SPY{expiry:%y%m%d}{direction[0]}{int(strike * 1000):08d}"
    return {"symbol": symbol, "strike": str(strike), "expiry": expiry.isoformat(),
            "direction": direction}


def order_payload(contract, client_id, side, limit=None, quantity=1):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 5:
        raise BrokerError("INVALID_QUANTITY")
    quantity_text = str(quantity)
    order = {"client_order_id": client_id, "combo_type": "NORMAL",
             "order_type": "LIMIT" if side == "BUY" else "MARKET", "quantity": quantity_text,
             "option_strategy": "SINGLE", "side": side, "time_in_force": "DAY",
             "entrust_type": "QTY", "instrument_type": "OPTION", "market": "US",
             "symbol": "SPY", "position_intent": "BUY_TO_OPEN" if side == "BUY" else "SELL_TO_CLOSE",
             "legs": [{"side": side, "quantity": quantity_text, "symbol": "SPY",
                       "strike_price": contract["strike"], "option_expire_date": contract["expiry"],
                       "instrument_type": "OPTION", "option_type": contract["direction"], "market": "US"}]}
    if side == "BUY":
        if limit is None or not Decimal(str(limit)).is_finite() or Decimal(str(limit)) <= 0:
            raise BrokerError("INVALID_LIMIT")
        order["limit_price"] = str(limit)
    return order


def checked_quote(data, contract, now, premium_cap):
    if not isinstance(data, list):
        raise BrokerError("UNEXPECTED_QUOTE_RESPONSE")
    matches = [item for item in data if isinstance(item, dict) and item.get("symbol") == contract["symbol"]]
    if len(matches) != 1:
        raise BrokerError("ATM_CONTRACT_UNAVAILABLE")
    item = matches[0]
    age = now.timestamp() - int(item["quote_time"]) / 1000
    # The Webull sandbox serves delayed option quotes and reports the delay; allow exactly that much extra age.
    delay = item.get("delay_minutes")
    max_age = 30 + (int(delay) * 60 + 60 if isinstance(delay, (int, str)) and str(delay).isdigit() and 0 < int(delay) <= 20 else 0)
    ask, bid = Decimal(str(item["ask"])), Decimal(str(item["bid"]))
    if not -5 <= age <= max_age or not ask.is_finite() or not bid.is_finite() or not 0 < bid <= ask:
        raise BrokerError(f"INVALID_OR_STALE_QUOTE age={age:.0f}s bid={bid} ask={ask}")
    if Decimal(str(item["strike_price"])) != Decimal(contract["strike"]):
        raise BrokerError("CONTRACT_MISMATCH")
    # Buy at the observed ask, rounded up to a cent; never use underlying levels as premiums.
    from decimal import ROUND_CEILING
    limit = ask.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    if premium_cap is not None and limit > premium_cap:
        raise BrokerError("PREMIUM_CAP_EXCEEDED")
    return str(limit)


def checked_order(data, client_id, side, quantity=1):
    if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
        raise BrokerError("UNEXPECTED_ORDER_RESPONSE")
    orders = [item for item in data["orders"] if item.get("client_order_id") == client_id]
    if len(orders) != 1:
        raise BrokerError("ORDER_NOT_FOUND")
    order = orders[0]
    status = order["status"]
    filled = Decimal(str(order.get("filled_quantity", "0")))
    expected = Decimal(quantity)
    if order.get("side") != side or Decimal(str(order["total_quantity"])) != expected:
        raise BrokerError("ORDER_MISMATCH")
    if status not in {"PENDING", "SUBMITTED", "CANCELLED", "FILLED", "FAILED", "PARTIAL_FILLED"}:
        raise BrokerError("UNKNOWN_ORDER_STATUS")
    if not filled.is_finite() or filled < 0 or filled > expected:
        raise BrokerError("UNEXPECTED_FILL_QUANTITY")
    if status == "FILLED" and filled != expected:
        raise BrokerError("INCONSISTENT_FILL")
    if status == "PARTIAL_FILLED" and not 0 < filled < expected:
        raise BrokerError("INCONSISTENT_PARTIAL_FILL")
    return status, int(filled)


class SandboxBroker:
    def __init__(self, account_number, premium_cap, quantity=5):
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 5:
            raise BrokerError("INVALID_QUANTITY")
        self.trade = client_from_env()  # Rejects every host except api.sandbox.webull.com.
        sdk = self.trade.account_v2.client
        sdk.set_token_dir(os.environ.get("WEBULL_OPENAPI_TOKEN_DIR", ".local/webull-token"))
        from webull.data.data_client import DataClient
        self.data = DataClient(sdk)
        accounts = response_data(self.trade.account_v2.get_account_list())
        account_summary(accounts)
        matches = [a for a in accounts if a.get("account_number") == account_number
                   and a.get("account_type") == "CASH"]
        if len(matches) != 1:
            raise BrokerError("PAPER_ACCOUNT_NOT_FOUND")
        self.account_id = matches[0]["account_id"]
        self.premium_cap = premium_cap
        self.quantity = quantity

    def prepare(self, payload, client_id, now):
        contract = atm_contract(payload, now)
        quote = response_data(self.data.option_market_data.get_option_snapshot(contract["symbol"], "US_OPTION"))
        contract["limit"] = checked_quote(quote, contract, now, self.premium_cap)
        preview = response_data(self.trade.order_v3.preview_order(
            self.account_id, [order_payload(contract, client_id, "BUY", contract["limit"], self.quantity)]))
        if not isinstance(preview, dict) or "estimated_cost" not in preview:
            raise BrokerError("UNCONFIRMED_PREVIEW")
        cost = Decimal(str(preview["estimated_cost"]))
        if not cost.is_finite() or cost <= 0:
            raise BrokerError("INVALID_PREVIEW_COST")
        return contract

    def place(self, contract, client_id, side, quantity=None):
        quantity = self.quantity if quantity is None else quantity
        data = response_data(self.trade.order_v3.place_order(
            self.account_id, [order_payload(contract, client_id, side, contract.get("limit"), quantity)]))
        if not isinstance(data, dict) or data.get("client_order_id") != client_id or not data.get("order_id"):
            raise BrokerError("UNCONFIRMED_SUBMISSION")

    def detail(self, client_id, side, quantity=None):
        quantity = self.quantity if quantity is None else quantity
        return checked_order(response_data(self.trade.order_v3.get_order_detail(self.account_id, client_id)),
                             client_id, side, quantity)

    def cancel(self, client_id):
        response_data(self.trade.order_v3.cancel_order(self.account_id, client_id))


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
        trade_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,
        contract TEXT, buy_id TEXT NOT NULL UNIQUE, sell_id TEXT NOT NULL UNIQUE,
        submitted_at TEXT, exit_requested INTEGER NOT NULL DEFAULT 0,
        last_error TEXT, updated_at TEXT NOT NULL,
        filled_quantity INTEGER NOT NULL DEFAULT 0)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(paper_trades)")}
    if "filled_quantity" not in columns:
        db.execute("ALTER TABLE paper_trades ADD COLUMN filled_quantity INTEGER NOT NULL DEFAULT 0")


def enqueue(db, trade_id, canonical, now):
    # Separate namespace prevents IDs previously generated by the dry-run recorder being used.
    buy_id = uuid.uuid5(uuid.NAMESPACE_URL, "paper-buy:" + trade_id).hex
    sell_id = uuid.uuid5(uuid.NAMESPACE_URL, "paper-sell:" + trade_id).hex
    db.execute("INSERT INTO paper_trades (trade_id,payload,state,buy_id,sell_id,updated_at) VALUES (?,?,?,?,?,?)",
               (trade_id, canonical, "PREPARE", buy_id, sell_id, now.isoformat()))


class PaperWorker:
    def __init__(self, settings, broker, clock=None):
        self.settings, self.broker = settings, broker
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.stop_event = threading.Event()
        self.thread = None
        self.last_tick = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name="paper-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                # Never log SDK exception text or signed request/response bodies.
                pass
            self.stop_event.wait(5)

    def update(self, trade_id, **changes):
        changes["updated_at"] = self.clock().isoformat()
        with sqlite3.connect(self.settings.database, timeout=2) as db:
            columns = ",".join(f"{name}=?" for name in changes)
            db.execute(f"UPDATE paper_trades SET {columns} WHERE trade_id=?", (*changes.values(), trade_id))

    def tick(self):
        now = self.clock()
        self.last_tick = now
        with sqlite3.connect(self.settings.database, timeout=2) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM paper_trades WHERE state NOT IN ('CLOSED','SKIPPED') ORDER BY rowid LIMIT 1").fetchone()
        if not row:
            return
        row = dict(row)
        trade_id, state = row["trade_id"], row["state"]
        local = now.astimezone(NY)
        # Server-side cutoff remains effective if an exit webhook is lost.
        cutoff = (local.hour * 100 + local.minute >= 1559
                  or datetime.fromisoformat(json.loads(row["payload"])["timestamp"].replace("Z", "+00:00")).astimezone(NY).date() < local.date())
        paused = Path(self.settings.kill_file).exists()
        want_exit = bool(row["exit_requested"] or cutoff or paused)
        try:
            if state == "PREPARE":
                payload = json.loads(row["payload"])
                timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
                if want_exit or not 0 <= (now - timestamp).total_seconds() <= 90:
                    self.update(trade_id, state="SKIPPED", last_error="ENTRY_EXPIRED_OR_PAUSED")
                    return
                contract = self.broker.prepare(payload, row["buy_id"], now)
                self.update(trade_id, state="PREPARED", contract=json.dumps(contract), last_error=None)
            elif state == "PREPARED":
                # Recheck exit intent after preparation, before persisting a submission intent.
                signal_time = datetime.fromisoformat(json.loads(row["payload"])["timestamp"].replace("Z", "+00:00"))
                if want_exit or (now - signal_time).total_seconds() > 90 or (now - datetime.fromisoformat(row["updated_at"])).total_seconds() > 15:
                    self.update(trade_id, state="SKIPPED", last_error="ENTRY_EXPIRED_OR_PAUSED")
                    return
                with sqlite3.connect(self.settings.database, timeout=2) as db:
                    db.execute("BEGIN IMMEDIATE")
                    claimed = db.execute("UPDATE paper_trades SET state='BUY_SUBMITTING',submitted_at=?,updated_at=? WHERE trade_id=? AND state='PREPARED' AND exit_requested=0",
                                         (now.isoformat(), now.isoformat(), trade_id)).rowcount
                if not claimed:
                    return
                self.broker.place(json.loads(row["contract"]), row["buy_id"], "BUY")
                self.update(trade_id, state="BUY_PENDING", last_error=None)
            elif state in {"BUY_SUBMITTING", "BUY_PENDING", "BUY_CANCELLING"}:
                # A timed-out or interrupted submission is looked up, NEVER submitted again.
                quantity = self.settings.paper_quantity
                status, filled = self.broker.detail(row["buy_id"], "BUY", quantity)
                if status == "FILLED" and filled == quantity:
                    self.update(trade_id, state="FILLED", filled_quantity=filled, last_error=None)
                elif status in {"CANCELLED", "FAILED"}:
                    self.update(trade_id, state="FILLED" if filled else "CLOSED",
                                filled_quantity=filled, last_error=None)
                elif want_exit or state == "BUY_CANCELLING" or (now - datetime.fromisoformat(row["submitted_at"])).total_seconds() >= 60:
                    self.update(trade_id, state="BUY_CANCELLING", filled_quantity=filled)
                    self.broker.cancel(row["buy_id"])
            elif state == "FILLED" and want_exit:
                self.update(trade_id, state="SELL_SUBMITTING")
                self.broker.place(json.loads(row["contract"]), row["sell_id"], "SELL",
                                  int(row["filled_quantity"]))
                self.update(trade_id, state="SELL_PENDING", last_error=None)
            elif state in {"SELL_SUBMITTING", "SELL_PENDING"}:
                quantity = int(row["filled_quantity"])
                status, filled = self.broker.detail(row["sell_id"], "SELL", quantity)
                if status == "FILLED" and filled == quantity:
                    self.update(trade_id, state="CLOSED", last_error=None)
                elif status in {"CANCELLED", "FAILED"}:
                    self.update(trade_id, state="BLOCKED", last_error="EXIT_REQUIRES_RECONCILIATION")
        except Exception as error:
            safe_error = str(error) if isinstance(error, BrokerError) else "BROKER_CHECK_FAILED"
            if state == "PREPARE":
                self.update(trade_id, state="SKIPPED", last_error=safe_error)
            else:
                self.update(trade_id, last_error=safe_error)
