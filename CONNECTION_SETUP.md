# Latest sweep/retest script → Render → Webull sandbox

The original sweep/retest indicator emits plain text, which the strict JSON
receiver rejects. Use `spy_sweep_retest_webhook.pine` for this pipeline. It keeps
the sweep/displacement/retest rules and emits JSON only after a later observed
underlying entry-level touch. A planned setup alone does not send an entry.
This remains close-confirmed: a touch is not proof of a broker limit fill, and
the worker buys the option at a fresh quoted ask, not at the SPY reference price.
SPY levels are not option premiums. There is no established profitable edge.

The new source remains uncompiled in TradingView. Default real-order-flow data
gating remains intact, and sandbox alerts default off. No synthetic order flow
is introduced. Before enabling it, connect verified external sources or explicitly
choose price-action-only research, compile, and replay/paper-test the script.

## Render configuration

On the existing service's Environment page, securely configure:

| Name | Setting |
| --- | --- |
| WEBULL_APP_KEY | Replacement GPTPAPER sandbox key, private |
| WEBULL_APP_SECRET | Replacement sandbox signing secret, private |
| WEBULL_ACCOUNT_NUMBER | Verified CASH sandbox account number, not App ID |
| WEBULL_SANDBOX_HOST | api.sandbox.webull.com |
| WEBULL_OPENAPI_TOKEN_DIR | /var/data/webull-token |
| WEBHOOK_TOKEN | Existing private receiver token; preserve it |
| PAPER_TRADING_ENABLED | false until preflight is verified; true starts worker |

No secrets are included in source or alert screenshots. The official SDK may
require its own Webull token/2FA verification. This is not a TradingView login
or a Webull desktop-session connection. Token storage is now configured before
the SDK initializes authentication.

When paper startup fails, the new app reports `status: degraded`,
`broker_orders_enabled: false`, and a sanitized `paper_startup_error` on /health,
instead of failing deployment with a generic message and leaving an older
dry-run revision active. It rejects new paper entries while the worker is
unavailable. `deployment_commit` identifies the revision actually serving traffic.
HTTP health alone is not brokerage readiness.

## Preflight without sending an order

Use Render Shell or a trusted local terminal with access to your private
`WEBHOOK_TOKEN`. Perform:

`POST https://spy-paper-webhook.onrender.com/paper/preflight?price=CURRENT_SPY_PRICE&direction=CALL`

Supply `X-Webhook-Token` as a request header, not as a URL parameter. Preflight
checks the configured account, quotes and option preview; no order is queued.
Use an actual current price during the trading session. Do not send tokens
to this chat. Webull business schemas and account permissions must be verified
against the actual sandbox response; passing mocked tests is not sufficient.

## TradingView alerts

Create a new indicator from `spy_sweep_retest_webhook.pine`. Put the Render
receiver token into its private token input. Enable sandbox JSON alerts only
after the preceding checks. Create exactly one alert using **Any alert()
function call**, with URL `https://spy-paper-webhook.onrender.com/webhook`.
Recreate it after script/input changes. Stop old alerts separately; hiding the
old indicator does not stop its alerts.

The Pine cutoff is now 14:00 New York to match the existing paper worker. Entry
IDs and frozen original levels are reused in exit JSON. Historical plans do
not emit exit alerts unless a live entry alert was actually sent. Restarting
the script/alert requires reconciliation with the server's persisted state.

## Checks still required

Verify live script compilation, public deployment revision, credential/2FA
readiness, a successful sandbox preflight, receipt of valid JSON, and the full
paper buy/fill/cancel/exit lifecycle. No live-trading host is supported. ChatGPT
does not supervise trades continuously; the worker runs on Render. This chat
needs a separately configured connector/API credential to inspect Render, and
cannot control the user's browser merely because its URL is visible.
