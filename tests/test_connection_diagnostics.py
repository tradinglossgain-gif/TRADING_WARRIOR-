from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import Settings, create_app


def test_missing_paper_credentials_reports_degraded_and_never_queues(tmp_path, monkeypatch):
    for name in ("WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_NUMBER"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings("x" * 40, str(tmp_path / "db"), str(tmp_path / "PAUSED"), paper_enabled=True)
    now = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)
    with TestClient(create_app(settings, lambda: now)) as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded" and health["mode"] == "paper"
        assert health["paper_startup_error"] == "MISSING_WEBULL_APP_KEY_AND_WEBULL_APP_SECRET_AND_WEBULL_ACCOUNT_NUMBER"
        assert not health["worker_running"] and not health["broker_orders_enabled"]
        alert = dict(token=settings.token, trade_id="sweep-1", timestamp=now.isoformat(),
                     action="ENTRY", symbol="SPY", direction="CALL", entry=600, stop=599, target=602)
        assert client.post("/webhook", json=alert).status_code == 503
        assert client.get("/health").json()["paper_states"] == {}


def test_sdk_exception_body_is_not_exposed(tmp_path, monkeypatch, caplog):
    import paper
    for name in ("WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_NUMBER"):
        monkeypatch.setenv(name, "secret-value")
    def fail(*args):
        raise RuntimeError("signed-request-secret-value")
    monkeypatch.setattr(paper, "SandboxBroker", fail)
    settings = Settings("x" * 40, str(tmp_path / "db"), str(tmp_path / "PAUSED"), paper_enabled=True)
    with TestClient(create_app(settings)) as client:
        body = client.get("/health").text
        assert "SANDBOX_STARTUP_FAILED" in body
        assert "secret-value" not in body and "secret-value" not in caplog.text


def test_token_directory_is_set_before_sdk_initializes_authentication(monkeypatch):
    import webull.core.client
    import webull.trade.trade_client
    from broker_check import client_from_env
    calls = []
    class SDK:
        def __init__(self, *args, **kwargs):
            pass
        def add_endpoint(self, region, host):
            assert host == "api.sandbox.webull.com"
        def set_token_dir(self, directory):
            calls.append(directory)
        def set_stream_logger(self, **kwargs):
            pass
    def trade(sdk):
        assert calls == ["/private/persistent/token"]
        return SimpleNamespace(account_v2=SimpleNamespace(client=sdk))
    monkeypatch.setattr(webull.core.client, "ApiClient", SDK)
    monkeypatch.setattr(webull.trade.trade_client, "TradeClient", trade)
    monkeypatch.setenv("WEBULL_APP_KEY", "test-key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "test-secret")
    monkeypatch.setenv("WEBULL_OPENAPI_TOKEN_DIR", "/private/persistent/token")
    client_from_env()
