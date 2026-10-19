"""Authenticated TradingView intake with optional sandbox-only paper execution."""
from contextlib import asynccontextmanager
from decimal import Decimal
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    token: str = Field(min_length=32, max_length=256)
    trade_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    action: Literal["ENTRY", "EXIT_SL", "EXIT_TP", "EXPIRE"] = "ENTRY"
    timestamp: datetime
    symbol: Literal["SPY"]
    direction: Literal["CALL", "PUT"]
    entry: float = Field(gt=0, lt=10000)
    stop: float = Field(gt=0, lt=10000)
    target: float = Field(gt=0, lt=10000)

    @model_validator(mode="after")
    def validate_levels(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        valid = (self.stop < self.entry < self.target if self.direction == "CALL"
                 else self.target < self.entry < self.stop)
        if not valid:
            raise ValueError("invalid SPY levels")
        return self


@dataclass(frozen=True)
class Settings:
    token: str
    database: str
    kill_file: str
    daily_limit: int = 5
    cooldown_seconds: int = 60
    paper_enabled: bool = False
    paper_account_number: str = ""
    paper_premium_cap: str = "3.00"
    paper_quantity: int = 5
    schwab_enabled: bool = False
    schwab_webhook_token: str = ""

    @classmethod
    def from_env(cls):
        token = os.environ.get("WEBHOOK_TOKEN", "")
        if not token and os.environ.get("WEBHOOK_TOKEN_FILE"):
            token = Path(os.environ["WEBHOOK_TOKEN_FILE"]).read_text().strip()
        if len(token) < 32:
            raise RuntimeError("Set WEBHOOK_TOKEN or WEBHOOK_TOKEN_FILE (minimum 32 characters)")
        mode = os.environ.get("PAPER_TRADING_ENABLED", "false")
        if mode not in {"true", "false"}:
            raise RuntimeError("PAPER_TRADING_ENABLED must be true or false")
        cap = os.environ.get("PAPER_PREMIUM_CAP", "3.00")
        if not Decimal(cap).is_finite() or Decimal(cap) <= 0:
            raise RuntimeError("PAPER_PREMIUM_CAP must be positive")
        try:
            quantity = int(os.environ.get("PAPER_QUANTITY", "5"))
        except ValueError:
            raise RuntimeError("PAPER_QUANTITY must be an integer from 1 to 5") from None
        if not 1 <= quantity <= 5:
            raise RuntimeError("PAPER_QUANTITY must be an integer from 1 to 5")
        schwab_mode = os.environ.get("SCHWAB_TRADING_ENABLED", "false")
        if schwab_mode not in {"true", "false"}:
            raise RuntimeError("SCHWAB_TRADING_ENABLED must be true or false")
        if schwab_mode == "true":
            raise RuntimeError(
                "Schwab Trader API cannot access thinkorswim PaperMoney; automated Schwab orders are disabled"
            )
        return cls(
            token=token,
            database=os.environ.get("DATABASE_PATH", ".local/events.sqlite3"),
            kill_file=os.environ.get("KILL_SWITCH_FILE", ".local/PAUSED"),
            paper_enabled=mode == "true",
            paper_account_number=os.environ.get("WEBULL_ACCOUNT_NUMBER", ""),
            paper_premium_cap=cap,
            paper_quantity=quantity,
            schwab_enabled=schwab_mode == "true",
            schwab_webhook_token=os.environ.get("SCHWAB_WEBHOOK_TOKEN", ""),
        )


def create_app(settings: Settings, clock=None, broker=None):
    from paper import PaperWorker, SandboxBroker, enqueue, initialize
    if settings.schwab_enabled:
        raise RuntimeError(
            "Schwab Trader API cannot access thinkorswim PaperMoney; automated Schwab orders are disabled"
        )
    clock = clock or (lambda: datetime.now(timezone.utc))
    Path(settings.database).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.database) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                payload TEXT NOT NULL, accepted_at TEXT NOT NULL,
                client_order_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS setups (
                trade_id TEXT PRIMARY KEY, direction TEXT NOT NULL,
                levels TEXT NOT NULL, day TEXT NOT NULL,
                accepted_at TEXT NOT NULL, active INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schwab_events (
                event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                payload TEXT NOT NULL, accepted_at TEXT NOT NULL,
                client_order_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS schwab_setups (
                trade_id TEXT PRIMARY KEY, direction TEXT NOT NULL,
                levels TEXT NOT NULL, day TEXT NOT NULL,
                accepted_at TEXT NOT NULL, active INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sim_trades (
                trade_id TEXT PRIMARY KEY, direction TEXT NOT NULL,
                entry REAL NOT NULL, stop REAL NOT NULL, target REAL NOT NULL,
                opened_at TEXT NOT NULL, closed_at TEXT, exit_action TEXT,
                exit_price REAL, pnl_points REAL
            );
        """)
        initialize(db)
    worker = None
    mode = "paper" if settings.paper_enabled else "dry_run"

    @asynccontextmanager
    async def lifespan(api):
        nonlocal worker
        if settings.paper_enabled:
            try:
                client = broker or SandboxBroker(settings.paper_account_number,
                                                 Decimal(settings.paper_premium_cap), settings.paper_quantity)
                worker = PaperWorker(settings, client, clock)
                api.state.paper_worker = worker
                worker.start()
            except Exception:
                raise RuntimeError("Paper worker startup failed; verify sandbox credentials and account configuration") from None
        try:
            yield
        finally:
            if worker:
                worker.stop()

    api = FastAPI(title="SPY TradingView receiver", docs_url=None, redoc_url=None, lifespan=lifespan)

    @api.get("/health")
    def health():
        with sqlite3.connect(settings.database) as db:
            state_counts = dict(db.execute("SELECT state,COUNT(*) FROM paper_trades GROUP BY state").fetchall())
            errors = db.execute("SELECT COUNT(*) FROM paper_trades WHERE last_error IS NOT NULL AND state NOT IN ('CLOSED','SKIPPED')").fetchone()[0]
        running = bool(worker and worker.thread and worker.thread.is_alive())
        return {"status": "ok", "mode": mode, "broker_orders_enabled": settings.paper_enabled and running,
                "schwab_broker_orders_enabled": False,
                "paused": Path(settings.kill_file).exists(), "worker_running": running,
                "paper_states": state_counts, "paper_reconciliation_required": errors > 0,
                "schwab_worker_running": False, "schwab_states": {},
                "schwab_reconciliation_required": False,
                "contract_policy": "SPY_0DTE_ATM", "paper_quantity": settings.paper_quantity,
                "paper_premium_cap": settings.paper_premium_cap}

    @api.post("/paper/preflight")
    def preflight(price: float = Query(gt=0, lt=10000),
                  direction: Literal["CALL", "PUT"] = "CALL",
                  x_webhook_token: str = Header(default="")):
        if not secrets.compare_digest(x_webhook_token.encode(), settings.token.encode()):
            raise HTTPException(401, "Invalid webhook token")
        try:
            now = clock()
            client = broker or SandboxBroker(settings.paper_account_number,
                                             Decimal(settings.paper_premium_cap), settings.paper_quantity)
            contract = client.prepare({"entry": price, "direction": direction,
                                       "timestamp": now.isoformat()}, uuid.uuid4().hex, now)
            return {"status": "preview_confirmed", "contract": contract,
                    "quantity": settings.paper_quantity,
                    "order_sent": False, "contract_policy": "SPY_0DTE_ATM"}
        except Exception:
            raise HTTPException(503, "Sandbox preflight failed; verify keys, account, quote access and option permissions") from None

    @api.post("/thinkorswim/preflight")
    def thinkorswim_preflight(x_webhook_token: str = Header(default="")):
        schwab_token = settings.schwab_webhook_token or settings.token
        if not secrets.compare_digest(x_webhook_token.encode(), schwab_token.encode()):
            raise HTTPException(401, "Invalid webhook token")
        raise HTTPException(
            409,
            "Schwab Trader API cannot preview thinkorswim PaperMoney; use the thinkorswim simulator directly",
        )

    @api.get("/thinkorswim/sim/trades")
    def sim_trades(x_webhook_token: str = Header(default="")):
        schwab_token = settings.schwab_webhook_token or settings.token
        if not secrets.compare_digest(x_webhook_token.encode(), schwab_token.encode()):
            raise HTTPException(401, "Invalid webhook token")
        with sqlite3.connect(settings.database, timeout=2) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("SELECT * FROM sim_trades ORDER BY opened_at")]
        closed = [r["pnl_points"] for r in rows if r["pnl_points"] is not None]
        return {"trades": rows,
                "summary": {"closed": len(closed), "open": len(rows) - len(closed),
                            "wins": sum(p > 0 for p in closed),
                            "total_pnl_points": round(sum(closed), 4)}}

    @api.post("/webhook")
    async def webhook(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "Send application/json")
        # Read bounded chunks rather than buffering an arbitrarily large request.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 8192:
                raise HTTPException(413, "Payload too large")
        try:
            alert = Alert.model_validate_json(bytes(body))
        except ValueError:
            # Never return Pydantic's input data: it can include the token.
            raise HTTPException(422, "Invalid alert schema, timestamp, or SPY levels")
        if not secrets.compare_digest(alert.token.encode(), settings.token.encode()):
            raise HTTPException(401, "Invalid webhook token")
        now = clock()
        age = (now - alert.timestamp).total_seconds()
        if age > 90 or age < -15:
            raise HTTPException(422, "Alert is stale or from the future")
        if Path(settings.kill_file).exists():
            raise HTTPException(503, "Receiver paused")
        payload = alert.model_dump(mode="json", exclude={"token"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        event_id = f"{alert.trade_id}:{alert.action}"
        order_id = uuid.uuid5(uuid.NAMESPACE_URL, event_id).hex
        levels = json.dumps([alert.entry, alert.stop, alert.target])
        local = now.astimezone(ZoneInfo("America/New_York"))
        day = local.date().isoformat()
        with sqlite3.connect(settings.database, timeout=2) as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT fingerprint FROM events WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise HTTPException(409, "Event ID reused with different data")
                return {"status": "duplicate", "mode": mode, "event_id": event_id}
            if alert.action == "ENTRY":
                hhmm = local.hour * 100 + local.minute
                if local.weekday() >= 5 or not 930 <= hhmm < 1555:
                    raise HTTPException(422, "Entries allowed weekdays 09:30–15:55 New York")
                if db.execute("SELECT 1 FROM setups WHERE active=1").fetchone():
                    raise HTTPException(409, "A signal setup is already active")
                if settings.paper_enabled and db.execute("SELECT 1 FROM paper_trades WHERE state NOT IN ('CLOSED','SKIPPED')").fetchone():
                    raise HTTPException(409, "A paper trade is pending, open, or requires reconciliation")
                count = db.execute("SELECT COUNT(*) FROM setups WHERE day=?", (day,)).fetchone()[0]
                if count >= settings.daily_limit:
                    raise HTTPException(429, "Daily signal limit reached")
                latest = db.execute("SELECT accepted_at FROM setups ORDER BY accepted_at DESC LIMIT 1").fetchone()
                if latest and (now - datetime.fromisoformat(latest[0])).total_seconds() < settings.cooldown_seconds:
                    raise HTTPException(429, "Signal cooldown active")
                if db.execute("SELECT 1 FROM setups WHERE trade_id=?", (alert.trade_id,)).fetchone():
                    raise HTTPException(409, "Trade ID already used")
                db.execute("INSERT INTO setups VALUES (?, ?, ?, ?, ?, 1)",
                           (alert.trade_id, alert.direction, levels, day, now.isoformat()))
                if settings.paper_enabled:
                    if not (worker and worker.thread and worker.thread.is_alive()):
                        raise HTTPException(503, "Paper worker unavailable")
                    enqueue(db, alert.trade_id, canonical, now)
            else:
                setup = db.execute("SELECT direction, levels, active FROM setups WHERE trade_id=?",
                                   (alert.trade_id,)).fetchone()
                if not setup or not setup[2]:
                    raise HTTPException(409, "No matching active signal setup")
                if setup[0] != alert.direction or setup[1] != levels:
                    raise HTTPException(409, "Exit does not match entry")
                db.execute("UPDATE setups SET active=0 WHERE trade_id=?", (alert.trade_id,))
                if settings.paper_enabled:
                    db.execute("UPDATE paper_trades SET exit_requested=1 WHERE trade_id=?", (alert.trade_id,))
            db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                       (event_id, fingerprint, canonical, now.isoformat(), order_id))
        return {"status": "queued" if settings.paper_enabled else "recorded", "mode": mode, "event_id": event_id,
                "broker_order_sent": False}

    @api.post("/thinkorswim/webhook")
    async def thinkorswim_webhook(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "Send application/json")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 8192:
                raise HTTPException(413, "Payload too large")
        try:
            alert = Alert.model_validate_json(bytes(body))
        except ValueError:
            raise HTTPException(422, "Invalid alert schema, timestamp, or SPY levels")
        schwab_token = settings.schwab_webhook_token or settings.token
        if not secrets.compare_digest(alert.token.encode(), schwab_token.encode()):
            raise HTTPException(401, "Invalid webhook token")
        now = clock()
        age = (now - alert.timestamp).total_seconds()
        if age > 90 or age < -15:
            raise HTTPException(422, "Alert is stale or from the future")
        if Path(settings.kill_file).exists():
            raise HTTPException(503, "Receiver paused")
        payload = alert.model_dump(mode="json", exclude={"token"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        event_id = f"schwab:{alert.trade_id}:{alert.action}"
        order_id = uuid.uuid5(uuid.NAMESPACE_URL, event_id).hex
        levels = json.dumps([alert.entry, alert.stop, alert.target])
        local = now.astimezone(ZoneInfo("America/New_York"))
        day = local.date().isoformat()
        with sqlite3.connect(settings.database, timeout=2) as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT fingerprint FROM schwab_events WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise HTTPException(409, "Event ID reused with different data")
                return {"status": "duplicate", "mode": mode, "event_id": event_id}
            if alert.action == "ENTRY":
                hhmm = local.hour * 100 + local.minute
                if local.weekday() >= 5 or not 930 <= hhmm < 1555:
                    raise HTTPException(422, "Entries allowed weekdays 09:30–15:55 New York")
                if db.execute("SELECT 1 FROM schwab_setups WHERE active=1").fetchone():
                    raise HTTPException(409, "A signal setup is already active")
                count = db.execute("SELECT COUNT(*) FROM schwab_setups WHERE day=?", (day,)).fetchone()[0]
                if count >= settings.daily_limit:
                    raise HTTPException(429, "Daily signal limit reached")
                latest = db.execute("SELECT accepted_at FROM schwab_setups ORDER BY accepted_at DESC LIMIT 1").fetchone()
                if latest and (now - datetime.fromisoformat(latest[0])).total_seconds() < settings.cooldown_seconds:
                    raise HTTPException(429, "Signal cooldown active")
                if db.execute("SELECT 1 FROM schwab_setups WHERE trade_id=?", (alert.trade_id,)).fetchone():
                    raise HTTPException(409, "Trade ID already used")
                db.execute("INSERT INTO schwab_setups VALUES (?, ?, ?, ?, ?, 1)",
                           (alert.trade_id, alert.direction, levels, day, now.isoformat()))
                db.execute("INSERT INTO sim_trades (trade_id, direction, entry, stop, target, opened_at) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (alert.trade_id, alert.direction, alert.entry, alert.stop, alert.target, now.isoformat()))
            else:
                setup = db.execute("SELECT direction, levels, active FROM schwab_setups WHERE trade_id=?",
                                   (alert.trade_id,)).fetchone()
                if not setup or not setup[2]:
                    raise HTTPException(409, "No matching active signal setup")
                if setup[0] != alert.direction or setup[1] != levels:
                    raise HTTPException(409, "Exit does not match entry")
                db.execute("UPDATE schwab_setups SET active=0 WHERE trade_id=?", (alert.trade_id,))
                # Simulated fill: stop/target levels fill at that level; EXPIRE closes flat at entry.
                exit_price = {"EXIT_SL": alert.stop, "EXIT_TP": alert.target}.get(alert.action, alert.entry)
                sign = 1 if alert.direction == "CALL" else -1
                db.execute("UPDATE sim_trades SET closed_at=?, exit_action=?, exit_price=?, pnl_points=? "
                           "WHERE trade_id=?",
                           (now.isoformat(), alert.action, exit_price,
                            round(sign * (exit_price - alert.entry), 4), alert.trade_id))
            db.execute("INSERT INTO schwab_events VALUES (?, ?, ?, ?, ?)",
                       (event_id, fingerprint, canonical, now.isoformat(), order_id))
        return {"status": "recorded", "mode": "dry_run", "event_id": event_id,
                "broker_order_sent": False}

    return api


def application():
    return create_app(Settings.from_env())
