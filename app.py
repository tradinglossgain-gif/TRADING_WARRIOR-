"""TradingView alert intake. This service never places broker orders."""
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

from fastapi import FastAPI, HTTPException, Request
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

    @classmethod
    def from_env(cls):
        token = os.environ.get("WEBHOOK_TOKEN", "")
        if not token and os.environ.get("WEBHOOK_TOKEN_FILE"):
            token = Path(os.environ["WEBHOOK_TOKEN_FILE"]).read_text().strip()
        if len(token) < 32:
            raise RuntimeError("Set WEBHOOK_TOKEN or WEBHOOK_TOKEN_FILE (minimum 32 characters)")
        return cls(token, os.environ.get("DATABASE_PATH", ".local/events.sqlite3"),
                   os.environ.get("KILL_SWITCH_FILE", ".local/PAUSED"))


def create_app(settings: Settings, clock=None):
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
        """)
    api = FastAPI(title="SPY TradingView receiver", docs_url=None, redoc_url=None)

    @api.get("/health")
    def health():
        with sqlite3.connect(settings.database) as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": "dry_run", "broker_orders_enabled": False,
                "paused": Path(settings.kill_file).exists()}

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
                return {"status": "duplicate", "mode": "dry_run", "event_id": event_id}
            if alert.action == "ENTRY":
                hhmm = local.hour * 100 + local.minute
                if local.weekday() >= 5 or not 945 <= hhmm < 1530:
                    raise HTTPException(422, "Entries allowed weekdays 09:45–15:30 New York")
                if db.execute("SELECT 1 FROM setups WHERE active=1").fetchone():
                    raise HTTPException(409, "A signal setup is already active")
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
            else:
                setup = db.execute("SELECT direction, levels, active FROM setups WHERE trade_id=?",
                                   (alert.trade_id,)).fetchone()
                if not setup or not setup[2]:
                    raise HTTPException(409, "No matching active signal setup")
                if setup[0] != alert.direction or setup[1] != levels:
                    raise HTTPException(409, "Exit does not match entry")
                db.execute("UPDATE setups SET active=0 WHERE trade_id=?", (alert.trade_id,))
            db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                       (event_id, fingerprint, canonical, now.isoformat(), order_id))
        return {"status": "recorded", "mode": "dry_run", "event_id": event_id,
                "broker_order_sent": False}

    return api


def application():
    return create_app(Settings.from_env())
