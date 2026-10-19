# SPY TradingView webhook

An authenticated, persistent receiver for SPY CALL/PUT signals and SPY entry,
stop-loss, take-profit levels. Local runs default to dry run. Render defines a
Webull sandbox paper-trading service and a separate Thinkorswim alert-only
dry-run service. Schwab Trader API order submission is disabled because it
cannot connect to thinkorswim PaperMoney.

## Automatic paper execution

`paper.py` adds a durable sandbox-only execution worker. The Render blueprint is
configured with `PAPER_TRADING_ENABLED=true`; do not deploy until sandbox keys,
the verified cash-account number, and a five-contract preview are configured and
validated. Local runs remain dry-run unless the setting is explicitly enabled.
It selects today's SPY option at the nearest whole-dollar strike to the signal
entry price (half-dollar ties round upward), confirms that exact contract with
a fresh option snapshot, and buys five contracts at its quoted ask with a DAY
limit order. Quantity is configurable from 1 to 5 with `PAPER_QUANTITY` and
defaults to 5. Default premium cap: $3.00 per share ($300 per contract, up to
$1,500 premium for five contracts, before fees).
Unavailable contracts, invalid/stale quotes, and options above the cap are skipped.
No different strike or expiry is substituted.

Configure `WEBULL_APP_KEY` and `WEBULL_APP_SECRET` privately in Render.
Set `WEBULL_ACCOUNT_NUMBER` privately to the verified CASH sandbox account number.
Set `PAPER_QUANTITY` from 1 to 5; it defaults to 5.
SDK requests are restricted to `api.sandbox.webull.com`.
`WEBULL_OPENAPI_TOKEN_DIR=/var/data/webull-token` persists any SDK authentication token.

`POST /paper/preflight?price=SIGNAL_PRICE&direction=CALL`, with private header
`X-Webhook-Token`, checks account access, option quotes, and previews one order.
It never submits or queues an order. Never put the token in a URL.

`POST /thinkorswim/webhook` on the separate Render service records signals in
dry-run mode for manual testing in thinkorswim PaperMoney. It does not connect
to, control, or submit orders to the PaperMoney simulator. `/thinkorswim/preflight`
returns an explanation that PaperMoney is unavailable through the Trader API;
it does not make a broker request.

The same route also drives a local simulator: each ENTRY opens a simulated trade
at the alert's `entry`, and EXIT_SL / EXIT_TP / EXPIRE close it at the stop /
target / entry level. `GET /thinkorswim/sim/trades` (with `X-Webhook-Token`)
returns every trade plus a summary of open/closed trades, wins and total P&L in
SPY points. Fills are idealized underlying-price fills, not option prices.

Only future accepted entries are queued after enablement; old dry-run events
are never replayed. Contract, trade state, and deterministic buy/sell IDs persist
in SQLite. Uncertain submissions are looked up, never automatically resubmitted.
New entries are blocked while any paper order/position is unresolved. Unfilled
entries are cancelled after 60 seconds, and their final fill/cancellation status
must be confirmed. Partial entry fills are reconciled, and exit sells only the
quantity confirmed filled. Exit signals close the same filled contract using a
market SELL_TO_CLOSE order. A server-side 15:59 New York cutoff requests closure even
if an exit webhook is lost. In paper mode the pause file also requests closure
of worker-owned positions while blocking new entries. Broker outages and failed
exits require reconciliation. Never replace the database to bypass order state.
Use exactly one worker/process. `/health` reports worker status, aggregate paper
states and whether reconciliation is required.

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

`render.yaml` prepares two separate Python services and persistent disks:
`spy-paper-webhook` for Webull sandbox paper execution and
`thinkorswim-paper-alerts` for dry-run alert recording only. The Thinkorswim
service cannot connect to or place simulated orders in PaperMoney. These
services use paid instances/disks; check Render's current charges before
creating them. They have not been deployed. A free ephemeral service would
lose durable duplicate protection on restart, so it is not the configured
default.

1. Push these files to a GitHub repository accessible to your Render account.
   These local changes have not been committed or pushed by this setup.
2. In Render, create a Blueprint using `render.yaml` in that repository.
3. Confirm the Webull service health and configure its sandbox credentials
   privately. The Thinkorswim alert-only service health must report
   `mode: dry_run`, `schwab_broker_orders_enabled: false`, and
   `broker_orders_enabled: false`.
4. Copy each service's generated `WEBHOOK_TOKEN` privately into the matching
   Pine indicator instance. Do not send tokens to this chat or publish the
   indicator with tokens embedded. Webull or Schwab credentials never belong
   in TradingView alerts.
5. Use the Webull service's HTTPS `/webhook` URL for the Webull path. For manual
   PaperMoney testing, use the separate `thinkorswim-paper-alerts` service's
   HTTPS `/thinkorswim/webhook` URL; it only records TradingView alerts and
   never places broker orders. Create separate TradingView alert instances
   with the corresponding token and URL. No public endpoint is created by
   starting this application in the cloud workspace.

For an existing server, put this app behind an HTTPS reverse proxy on port 443,
keep one worker, persist the SQLite database, cap request bodies at 8 KiB,
apply edge rate limits, and redact request bodies from logs. Use a production
secret manager to inject `WEBHOOK_TOKEN` and persistent `DATABASE_PATH`.

## TradingView

Paste `spy_webhook.pine` into Pine Editor and add it to an intraday SPY chart,
preferably 5 minutes. This source has not been compiled in TradingView here.
Set the matching service's webhook token privately. For separate Webull and
manual PaperMoney destinations, use separate indicator instances with their
respective tokens, and create an alert for each instance with condition
**Any alert() function call** and its matching deployed HTTPS webhook URL.
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
day, and a 60-second entry cooldown. Entry times are weekdays 09:30–15:55 New
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

## Thinkorswim PaperMoney

Thinkorswim offers PaperMoney in its own platform, but Schwab Trader API does
not expose PaperMoney accounts or simulated order execution. Therefore,
`SCHWAB_TRADING_ENABLED` must remain `false`; the app rejects attempts to turn
on automated Schwab orders. Use `/thinkorswim/webhook` to record TradingView
alerts, then enter/test the corresponding trades manually in thinkorswim
PaperMoney. Do not provide Schwab or Chrome passwords to this app or chat.

## What remains before paper execution

Obtain a public HTTPS deployment, configure replacement credentials, confirm
sandbox options support, and verify account access plus an actual option
preview. Validate contract selection, submission, fill/status reconciliation,
cancellation, and closing the same filled option on the deployed sandbox.
The worker is implemented locally; local tests and previews alone do not confirm
activation. Render hosts the deployed worker. This chat is not a continuously
running trade supervisor.
