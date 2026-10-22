# SPY Structure + Macro Context v28

## What the supplied narrative does and does not establish

The uploaded text describes historical examples. Its claimed feed retrieval and news citations were not independently verified in this task. No quoted price, purported profitable turn, or reconstructed example is hard-coded. This is a prospective rule-based implementation, not proof that those examples were tradable or that the rules are profitable.

## Entry and risk rules

Run on standard SPY **1-minute candles**. Prior completed5m/30m/4h trend, prior completed day high/low/close and week high/low are requested internally. Default premarket range is04:00–09:30 New York and requires extended-session data to be available on the chart. Swings become available only after the configured right-hand confirmation bars; markers and entries are never backdated to the swing candle.

CALL: a completed candle dips through then reclaims a known low/support, or reclaims prior close from below. Freeze that candle's low and the last already-confirmed swing high. A later bullish displacement closes above that frozen high with minimum body/relative volume. Enter at confirmed close in Breakout or Retest mode; Retest only mode waits for a bullish held pullback to the broken high. PUT mirrors this: rejection at known high/resistance, break below frozen confirmed swing low, then breakout entry or failed rebound. A fresh extreme beyond the arming wick or15-bar expiry invalidates the sequence. One frame is tracked at a time; no same-bar exit/reentry.

Previous close is explicitly a **reclaim level**, never labeled previous-day-low liquidity. All OHLCV level interactions are price patterns, not observations of resting stops, hidden liquidity, absorption or institutional orders.

Stop is beyond the frozen invalidating wick plus0.1ATR buffer, with at least0.5ATR distance. Reject risk above3ATR rather than moving the stop closer. Final target is just before the nearest mapped opposing level; if none is mapped, label the2.5R fallback. Cap at3R; reject targets below1.5R. Targets and stop remain frozen. TP1 and TP2 are advisory partial-taking levels; only stop, FINAL TP or time exit closes the modeled full trade or sends a full-exit JSON. Stop has conservative priority if one OHLC candle touches stop and final target. These are underlying SPY levels, not option-premium levels or broker fills.

Every accepted setup creates red/green boxes, blue entry, red SL, dashed TP1/TP2, final target, and exact-price labels. Latest prices persist in the dashboard. Keep8 frames by default. FVG display is optional and is not an entry gate: bull=low>high[2], bear=high<low[2], confirmed at candle close. Thus absence of an FVG retest does not automatically suppress breakout entries.

## Technical and fundamental context

VWAP alignment is on by default. Completed5m trend gating is optional and off, allowing recovery trades against a slower trend. Relative volume is a candle-volume metric, not order flow. Closed30m/4h trend is contextual.

TVC:US10Y supplies yield-percentage context if TradingView provides it.15-minute change is shown in basis points, with optional3bps directional spike filter. If enabled and unavailable, entries are blocked. XLK/XLF/XLY participation is a3-sector price proxy, **not actual advancing/declining market breadth**. Missing feeds display unavailable.

No live CPI actual-versus-consensus, earnings surprises, Fed speeches, news or economic calendar is claimed. The fundamental integration is a dated reviewed Bullish/Bearish/Neutral/No-trade bias and a dated manually entered event exclusion. Enable only after entering your reviewed information and validity interval. Expired bias blocks entries when enabled. Event overlap blocks entries. Manual historical bias can create hindsight; this is not a point-in-time fundamental backtest.

## Optional paper webhook token and protocol

Default OFF with token blank; contracts default5, bounded1–20. Indicator Settings -> **5 — Optional PAPER webhook JSON** -> Private WEBHOOK_TOKEN. Keep token private, matching the receiver environment value; it is not a broker password/key. TradingView input.string does not securely mask it in screenshots.

After receiver validation, enable JSON and create one TradingView alert: Condition=this indicator -> **Any alert() function call**. Notifications -> Webhook URL=your receiver HTTPS endpoint, e.g.https://spy-paper-webhook.onrender.com/webhook. Do not put the URL in the token field. Recreate the alert after changing source, token, quantity, time windows or other inputs: old alerts retain their snapshots. Disable old alerts separately.

Protocol fields: token, trade_id, source_version="structure_v28", action in ENTRY/EXIT_SL/EXIT_TP/EXPIRE, UTC timestamp, symbol SPY, direction CALL/PUT, original frozen entry/stop/final target, frozen quantity. No historical orders are emitted. JSON uses timenow in realtime. Only frames whose ENTRY JSON was emitted can emit exit JSON. TP1/TP2 do not send full-exit alerts. Contract/quantity must be retained by the receiver; strike reference is nearest whole-dollar ATM at entry, not an actual selected/quoted/filled contract.

**Existing deployed receiver versions do not accept structure_v28.** A compatible five-contract sandbox receiver is included separately in structure-v28-paper-receiver, with31 mocked tests passed. It has not been deployed. No production service, key or broker order was changed.

The prepared receiver retains its existing14:00 New York paper cutoff. Therefore PAPER JSON defaults to09:45–13:55 new entries and14:00 exit, independently of chart entries until15:50 and chart cutoff15:55. Afternoon chart setups remain visual-only. A14:00 JSON EXPIRE ends the paper trade even if the chart frame continues; later chart exits do not emit a second paper exit. Match paper windows to receiver policy before enabling. Do not assume this bundle automates the narrative's14:56 example; extending paper hours requires coordinated receiver-policy changes and validation.

## Validation and remaining checks

Source checks: one indicator declaration, balanced delimiters, frozen exit payload fields, real-time-only entries, bounded drawings, and causal completed-timeframe requests. Receiver tests:31 passed with mocked broker interactions, including structure_v28 intake, five-contract quantities, idempotency, partial-fill handling and matching exits. No real order submitted.

No native TradingView compiler, visual rendering or historical market replay was available here. Pine compilation, on-chart behavior and performance remain unverified. The macro proxies are not independently verified live data in this task. No profitability or complete automation readiness is claimed. Load/compile, inspect a full historical session, and verify sandbox ENTRY -> order acknowledgement -> fill -> matching EXIT before relying on automation.
