# SPY TradingView webhook

An authenticated, persistent receiver for SPY CALL/PUT signals and SPY entry,
stop-loss, take-profit levels. **Current mode is dry run: alerts are recorded,
and no Webull order is sent.** Webull connectivity and options support in the
PaperTrade sandbox remain unverified. No live trading endpoint is enabled.

## Run locally

Use the existing isolated checkout; do not create a Git worktree for setup.
Python 3.12 is the tested runtime.

```sh
cd /workspace/TRADING_WARRIOR-
bash scripts/setup.sh
.venv/bin/python -m pytest -q
bash scripts/start.sh
```

Setup generates a random local webhook token in `.local/webhook-token`, with
owner-only permissions, without printing it. Setup preserves an existing token.
The database survives restarts. Processes must be restarted in future tasks.
`GET /health` reports `mode: dry_run` and `broker_orders_enabled: false`.

## Deploy on Render

`render.yaml` prepares one Python service and a persistent disk. This uses a
paid service/disk; check Render's current charges before creating it. It has
not been deployed. A free ephemeral service would lose durable duplicate
protection on restart, so it is not the configured default.

1. Push these files to a GitHub repository accessible to your Render account.
   These local changes have not been committed or pushed by this setup.
2. In Render, create a Blueprint using `render.yaml` in that repository.
3. Confirm service health in Render. It must report `dry_run`.
4. Copy Render's generated `WEBHOOK_TOKEN` securely into the Pine indicator's
   token input. Do not send the token to this chat or publish the indicator
   with your token embedded. Webull keys never belong in TradingView alerts.
5. Use the deployed service's HTTPS `/webhook` URL in TradingView. No public
   endpoint is created by starting this application in the cloud workspace.

For an existing server, put this app behind an HTTPS reverse proxy on port 443,
keep one worker, persist the SQLite database, cap request bodies at 8 KiB,
apply edge rate limits, and redact request bodies from logs. Use a production
secret manager to inject `WEBHOOK_TOKEN` and persistent `DATABASE_PATH`.

## TradingView

Paste `spy_webhook.pine` into Pine Editor and add it to an intraday SPY chart,
preferably 5 minutes. This source has not been compiled in TradingView here.
Set the webhook token privately. Create **one** alert with condition
**Any alert() function call**, and enter your deployed HTTPS webhook URL.
Webhook availability depends on your TradingView plan; enable two-factor
authentication if TradingView requires it. Recreate the alert after changing
the script or its inputs: TradingView runs a saved copy.

The script emits JSON automatically at candle close. It combines VWAP, 9/21
EMAs, five-bar breakouts, and OHLCV volume pressure. The pressure measure is a
proxy, not real options order flow or bid/ask delta. Entry, SL, and TP are SPY
prices, not option premiums. If both stop and target are touched in one bar,
the script assumes the stop first; this is not a tick-level execution model.
Exit alerts arrive at candle close, so they are not broker stop orders.
Session expiry needs a subsequent bar outside regular hours; on regular-hours
only charts this may not arrive until later. No scheduled flatten is implemented.

### JSON contract

```json
{
  "token": "REPLACE_WITH_YOUR_PRIVATE_WEBHOOK_TOKEN",
  "trade_id": "SPY-5-UNIQUE_BAR_TIMESTAMP",
  "action": "ENTRY",
  "timestamp": "REPLACE_WITH_CURRENT_UTC_ISO_TIMESTAMP",
  "symbol": "SPY",
  "direction": "CALL",
  "entry": 600.00,
  "stop": 599.00,
  "target": 602.00
}
```

Use `PUT` with `target < entry < stop`. Exit actions are `EXIT_SL`, `EXIT_TP`,
or `EXPIRE`, using the original trade ID, direction and levels, with a fresh
timestamp. Exact duplicates are acknowledged without a second record;
conflicting reuse of an event ID is rejected. Tokens are never stored in the
event database or returned in validation errors.

Alerts older than 90 seconds or over 15 seconds in the future are rejected.
The receiver allows one active **signal setup**, five entries per New York
day, and a 60-second entry cooldown. Entry times are weekdays 09:45–15:30 New
York; this is not an exchange holiday calendar. An active setup is not evidence
of a filled position. If an exit delivery is missed, later entries are blocked:
pause and reconcile the signal records before resuming. Do not delete the
database to bypass duplicate protection. Alert/script restarts also require
reconciliation because prior entry-notification state does not survive in Pine.

Pause locally with `touch .local/PAUSED`; resume with `rm .local/PAUSED` after
reconciliation. On Render use `/var/data/PAUSED`. This pauses intake; it does not
close positions or cancel broker orders. Keep the token out of request logs.

## Webull prerequisites and read-only checks

The prior paper credentials were exposed in a screenshot. Revoke/reset those
and use a replacement pair, securely injected into the deployment:

- `WEBULL_APP_KEY`, `WEBULL_APP_SECRET`: raw SDK signing credentials.
- `WEBULL_SANDBOX_HOST`: optional; defaults to `api.sandbox.webull.com`.
- `WEBULL_ACCOUNT_ID`: sandbox account identifier, needed for an option preview.

No credential values are included in this repository. Proxy-injected secret
placeholders cannot be used to perform the SDK's local request signature;
configure raw signing credentials securely on your chosen host. This sandbox
hostname is verified in Webull's official Getting Started and SDK documentation.
The helper allows only `api.sandbox.webull.com`; other hosts are rejected.

```sh
.venv/bin/python broker_check.py accounts
.venv/bin/python broker_check.py preview --direction CALL --strike ACTUAL_STRIKE --expiry YYYY-MM-DD --limit OPTION_PREMIUM_LIMIT
```

The official SDK is pinned to `webull-openapi-python-sdk==3.0.2`. The helper
uses `account_v2.get_account_list` or `order_v2.preview_option`, never a
place-order method. Preview requires an explicit contract, one contract only,
and a premium limit up to $3.00 ($300 before fees). SPY price levels must not
be used as option premiums. An HTTP 200 is reported only as HTTP success, not
as confirmed business success. Broker response data are not dumped into logs.
The SDK may require Webull's own 2FA flow; it has not been verified here.

Official references:
- https://developer.webull.com/apis/docs/getting-started
- https://developer.webull.com/apis/docs/sdk
- https://github.com/webull-inc/webull-openapi-python-sdk

The documentation is now accessible from this environment. Trading API uses
`api.sandbox.webull.com`; the separate partner OAuth Connect API uses
`oauth-open-api.sandbox.webull.com` and is not the App Key SDK integration
implemented here. API access still requires sandbox networking and configured
credentials. Documentation lists options among supported OpenAPI products,
but GPTPAPER account permissions and an actual option preview remain unverified.

## What remains before paper execution

Obtain a public HTTPS deployment, configure replacement credentials, confirm
sandbox options support, and verify account access plus an actual option
preview. Then implement and validate contract selection, order submission,
fill/status reconciliation, cancellations, and exits on the same filled option
contract. This receiver intentionally has no order-submission worker yet;
changing environment variables cannot enable trading. Broker integration cannot
be validated without those external prerequisites. ChatGPT is not connected to
the account and this chat is not a continuously running trade supervisor.
