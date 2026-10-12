# v21: existing visual build with the supplied AMD liquidity method

`spy_options_amd_sweep_v21.pine` is a complete replacement indicator, retaining
the original EMA/Hull/VWAP plots, dashboard, TP/SL lines, risk/reward boxes,
completed trade frames and option-reference labels. Its entry engine is changed.
No profitability claim is made. Pine compilation and TradingView execution
have not been verified here.

## What changed

- Adapted the supplied **AMD Liquidity Sweep with Alerts** intermediate-pivot
  classification: a lower subsequent pivot confirms an intermediate high;
  a higher subsequent pivot confirms an intermediate low. The original
  additional one-bar confirmation lag is retained. Initial bootstrap pivots
  are excluded until a real higher-high/lower-high or lower-low/higher-low
  sequence is observed.
- Levels are available only when their classification confirms. They are
  calculated on every closed bar instead of only `barstate.islast`, bounded
  to 64 levels per side and reset each New York day. No backdated entry arrows.
- A CALL requires sellside liquidity to be penetrated and reclaimed on a
  closed candle. A PUT requires buyside penetration and a close back below it.
  Merely crossing through a level is not an entry.
- A separate later candle must displace through frozen pre-sweep structure;
  another later candle must retest and hold it. Setups expire or are invalidated
  by a return to the sweep extreme. Consumed levels cannot be reused that day
  within the retained level history.
- All entry filter modes require that sequence. The previous EMA-pullback,
  VWAP-reclaim and original-score modes cannot bypass it. Score filtering is
  enabled by default, but scores remain heuristic, not success probabilities.
- Initial stops are beyond the sweep wick using the frozen sweep ATR buffer.
  Old initial-stop controls that no longer applied were removed. Excessive
  risk and insufficient room to recorded opposing liquidity reject entries.
- Automatic exits and trailing updates are evaluated on closed candles to
  avoid intrabar state rollback. New trailing stops apply on subsequent bars.
  Closed-candle alerts can be delayed; these are not broker stop orders.
- The decorative volume cells are labeled **EST BUY / EST SELL / EST Δ**.
  They remain estimates derived from candle shape, not actual aggressor order
  flow. They do not prove absorption, institutional activity or buying pressure.
- Strict option-premium mode requires sources identified as actual options;
  it cannot silently treat the SPY share chart as option premium. It is disabled
  for sandbox webhook mode because those chart contracts have not been matched
  to the contract independently selected by the worker.

## Defaults and chart setup

Use standard SPY 1–5 minute candles, preferably five minutes, with extended-hours
data enabled. The AMD filter defaults to intermediate levels outside the
**04:00–09:30 New York premarket range** rather than the original timezone-implicit
Asia range. Missing premarket bars can therefore block signals. You may explicitly
disable that range filter to test intraday intermediate levels; the sweep,
displacement and retest requirements still remain mandatory.

The dashboard reports WAIT AMD SWEEP, SWEEP → WAIT BREAK and BREAK → WAIT RETEST.
You should expect fewer signals. Lack of a qualified signal is not a code failure.
Target-room validation can also reject a clean-looking retest. No benchmark shows
that these particular defaults improve returns; calibrate on independent data.

Keep the existing boxes and plot styles, and hide the old indicator only after
this version compiles. **Stop the old alerts separately.** Changing a chart
indicator does not update TradingView's saved alert copy. Do not run competing
automated alerts from both versions.

## Sandbox JSON compatibility

The default is OFF. Configure the private receiver token and enable sandbox
JSON only after compilation and replay/paper validation. That mode requires
automatic signal tracking, one contract, whole-dollar strikes, 0DTE and the
14:00 New York cutoff to match the existing worker. The UI labels the worker's
ATM contract policy instead of implying the displayed ITM reference will be used.

Create one **Any alert() function call** alert pointing to:
`https://spy-paper-webhook.onrender.com/webhook`.

Messages identify `source_version: amd_sweep_v1`. The backend must permit that
version. Human advisory alerts are suppressed in JSON mode, so text TP1 alerts
are not confused with executable exit events. Entry JSON is emitted only when
the indicator accepts the confirmed signal on a realtime closed bar. Exits
reuse the original trade ID and frozen original SPY entry/stop/target levels,
even when the displayed trailing stop has moved. Historical entries never emit
paper orders. Reloading/recreating an alert requires reconciliation with any
paper positions already tracked on Render.

SPY reference levels do not specify an option's execution price or dollar risk.
The existing worker independently selects an ATM option and buys at a freshly
quoted ask within its premium cap; it does not follow an ITM contract reference
or assume the indicator's theoretical entry was a real fill. Its dollar premium
cap is a purchase cap, not a guaranteed stop-loss cap.

## Validation limits

Source delimiter checks and backend JSON-contract tests do not compile Pine,
prove the absence of every repainting issue or validate profitability. Verify
the actual indicator in Pine Editor, then replay against several sessions and
paper-test the alert/fill/exit sequence. Prices may gap through stops, and OHLC
bars cannot establish the true ordering of stop and target touches. The existing
engine conservatively checks the prior stop first when both levels are touched.

The original script is an indicator, not an options backtest. Its SPY-point P&L
labels exclude option spreads, execution, volatility, time decay and fees.
Popularity of a source indicator would not establish a profitable edge; no
popularity claim was verified for the supplied AMD script.
