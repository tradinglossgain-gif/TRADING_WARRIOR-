import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import Settings, create_app
from paper import (BrokerError, PaperWorker, atm_contract, checked_order,
                   checked_quote, enqueue, order_payload)


class FakeBroker:
    def __init__(self):
        self.placements = []
        self.cancellations = []
        self.status = ("PENDING", 0)
        self.fail_after_place = False

    def prepare(self, payload, client_id, now):
        return {**atm_contract(payload, now), "limit": "1.36"}

    def place(self, contract, client_id, side):
        self.placements.append((contract, client_id, side))
        if self.fail_after_place:
            raise TimeoutError("secret SDK exception must not be stored")

    def detail(self, client_id, side):
        return self.status

    def cancel(self, client_id):
        self.cancellations.append(client_id)


@pytest.fixture
def worker(tmp_path):
    now = [datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)]
    settings = Settings("x" * 40, str(tmp_path / "db.sqlite3"), str(tmp_path / "PAUSED"))
    create_app(settings, lambda: now[0])
    payload = {"trade_id": "SPY-5-test", "timestamp": now[0].isoformat(), "symbol": "SPY",
               "direction": "CALL", "entry": 778.62, "stop": 777, "target": 782}
    with sqlite3.connect(settings.database) as db:
        enqueue(db, payload["trade_id"], json.dumps(payload), now[0])
    fake = FakeBroker()
    return PaperWorker(settings, fake, lambda: now[0]), fake, now, payload


def row(worker):
    with sqlite3.connect(worker.settings.database) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM paper_trades").fetchone())


def test_atm_0dte_and_close_intent(worker):
    w, fake, now, payload = worker
    c = atm_contract(payload, now[0])
    assert c["strike"] == "779" and c["expiry"] == "2026-10-12"
    assert c["symbol"] == "SPY261012C00779000"
    order = order_payload(c, "id", "SELL")
    assert order["position_intent"] == "SELL_TO_CLOSE" and order["quantity"] == "1"
    assert "limit_price" not in order
    with pytest.raises(BrokerError):
        atm_contract(payload, now[0] + timedelta(days=1))


def test_duplicate_worker_ticks_never_duplicate_buy_and_exit_uses_same_contract(worker):
    w, fake, now, payload = worker
    w.tick()  # prepare
    w.tick()  # submit once
    for _ in range(3):
        w.tick()
    assert len(fake.placements) == 1 and row(w)["state"] == "BUY_PENDING"
    fake.status = ("FILLED", 1)
    w.tick()
    w.update(payload["trade_id"], exit_requested=1)
    w.tick()
    assert len(fake.placements) == 2
    assert fake.placements[0][0] == fake.placements[1][0]
    assert fake.placements[1][2] == "SELL"
    w.tick()
    assert row(w)["state"] == "CLOSED"
    w.tick()
    assert len(fake.placements) == 2


def test_timeout_and_restart_look_up_instead_of_resubmitting(worker):
    w, fake, now, payload = worker
    fake.fail_after_place = True
    w.tick()
    w.tick()
    assert row(w)["state"] == "BUY_SUBMITTING"
    assert "secret" not in row(w)["last_error"]
    restarted = PaperWorker(w.settings, fake, lambda: now[0])
    restarted.tick()
    assert len(fake.placements) == 1


def test_exit_before_submission_and_stale_entry_are_skipped(worker):
    w, fake, now, payload = worker
    w.tick()
    w.update(payload["trade_id"], exit_requested=1)
    w.tick()
    assert row(w)["state"] == "SKIPPED" and not fake.placements


def test_unfilled_order_is_cancelled_then_fill_race_is_reconciled(worker):
    w, fake, now, payload = worker
    w.tick()
    w.tick()
    now[0] += timedelta(seconds=61)
    w.tick()
    assert fake.cancellations and row(w)["state"] == "BUY_CANCELLING"
    w.update(payload["trade_id"], exit_requested=1)
    fake.status = ("FILLED", 1)
    w.tick()
    w.tick()
    assert len(fake.placements) == 2 and fake.placements[-1][2] == "SELL"


def test_server_cutoff_closes_filled_trade_without_exit_alert(worker):
    w, fake, now, payload = worker
    w.tick()
    w.tick()
    fake.status = ("FILLED", 1)
    w.tick()
    now[0] = now[0].replace(hour=18)  # 14:00 New York
    w.tick()
    assert fake.placements[-1][2] == "SELL"


def test_invalid_quotes_and_fill_business_status_fail_closed(worker):
    w, fake, now, payload = worker
    c = atm_contract(payload, now[0])
    quote = {"symbol": c["symbol"], "quote_time": int(now[0].timestamp()*1000),
             "strike_price": "779", "bid": "1.35", "ask": "1.36"}
    assert checked_quote([quote], c, now[0], Decimal("3")) == "1.36"
    for changes in ({"quote_time": 1}, {"ask": "3.01"}, {"bid": "2"}, {"symbol": "wrong"}):
        with pytest.raises(BrokerError):
            checked_quote([{**quote, **changes}], c, now[0], Decimal("3"))
    for data in ({"error_code": "DENIED"}, {"orders": []},
                 {"orders": [{"client_order_id": "id", "side": "BUY", "total_quantity": "1",
                               "filled_quantity": "0", "status": "FILLED"}]}):
        with pytest.raises(BrokerError):
            checked_order(data, "id", "BUY")


def test_dry_run_records_are_not_replayed_into_paper_orders(worker):
    w, fake, now, payload = worker
    with sqlite3.connect(w.settings.database) as db:
        db.execute("DELETE FROM paper_trades")
        db.execute("INSERT INTO events VALUES ('historical','hash','{}',?,'old-id')", (now[0].isoformat(),))
    w.tick()
    assert not fake.placements


def test_paper_intake_atomically_queues_and_blocks_next_entry_until_close(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    monkeypatch.setattr(PaperWorker, "start", lambda self: setattr(self, "thread", SimpleNamespace(
        is_alive=lambda: True, join=lambda timeout: None)))
    now = [datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)]
    settings = Settings("x" * 40, str(tmp_path / "db"), str(tmp_path / "PAUSED"), paper_enabled=True)
    fake = FakeBroker()
    payload = {"token": settings.token, "trade_id": "trade-1", "timestamp": now[0].isoformat(),
               "symbol": "SPY", "direction": "CALL", "entry": 778.62, "stop": 777, "target": 782}
    with TestClient(create_app(settings, lambda: now[0], fake)) as client:
        assert client.post("/webhook", json=payload).json()["status"] == "queued"
        assert client.post("/webhook", json=payload).json()["status"] == "duplicate"
        with sqlite3.connect(settings.database) as db:
            assert db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1
        assert client.post("/webhook", json={**payload, "action": "EXIT_SL"}).status_code == 200
        now[0] += timedelta(seconds=61)
        assert client.post("/webhook", json={**payload, "trade_id": "trade-2", "timestamp": now[0].isoformat()}).status_code == 409
        client.app.state.paper_worker.tick()
        assert not fake.placements
        assert client.get("/health").json()["paper_states"] == {"SKIPPED": 1}


def test_preflight_requires_authentication_and_never_places_or_queues(worker):
    from fastapi.testclient import TestClient
    w, fake, now, payload = worker
    with TestClient(create_app(w.settings, lambda: now[0], fake)) as client:
        assert client.post("/paper/preflight?price=778.62").status_code == 401
        result = client.post("/paper/preflight?price=778.62", headers={"X-Webhook-Token": w.settings.token})
        assert result.json()["status"] == "preview_confirmed" and not fake.placements
        with sqlite3.connect(w.settings.database) as db:
            assert db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1
