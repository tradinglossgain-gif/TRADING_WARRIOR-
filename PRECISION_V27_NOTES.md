# Precision Trend & Entry v27 — modification of uploaded strategy

## Concrete fixes

- Correct `//@version=6`, one strategy declaration.
- Select EMA Cross (default), original Trend Pullback, or Both. Default EMAs10/20; configurable. EMA20/50 trend pullbacks remain available by settings.
- Every accepted entry immediately creates a green target box, red risk box, four horizontal lines and four exact-price labels: SIGNAL ENTRY, STOP LOSS, TP1, TP2. Prices appear inside the boxes as well as the dashboard, so labels are not the only indication of levels. Retain8 frames by default. Arrays bound retained frames and rejection labels to stay under drawing quotas.
- Freeze levels at acceptance. Initial stop is the farther of buffered recent swing and1.2ATR distance. Targets1R/2R by default. These are risk-based targets, not predictions of future liquidity or guaranteed option premiums.
- Send both protective strategy.exit brackets on the entry calculation, not one bar later after position_size becomes nonzero. Each bracket reserves a fixed half of the original underlying-share quantity. Do not repeatedly resize to half of a shrinking remaining position. First-tranche status comes from strategy closed-trade records, not candle-wick guesses.
- Default session09:30–16:00 New York with15:55 cutoff. Change to14:00 if desired. Cutoff checks bar-close time after the chosen time; it does not depend on one five-minute session being present.
- Plain strategy alert() notifications replace ineffective strategy alertcondition calls. They are NOT compatible Webull order JSON.

## Technical and fundamental context

Optional technical confluence combines session VWAP, DMI/ADX, RSI, relative volume and previous COMPLETED15-minute EMA20 alignment. It is off by default to keep the requested EMA-cross behavior visible. Turn it on in Settings for filtered entries. Tiny cross markers remain visible; rejected entry labels explain the first blocker. The15m request offsets the expression before lookahead_on, so it does not read future higher-timeframe prices.

There is no universally best profitable combination. SPY/QQQ are ETFs; corporate financial ratios are not provided as intraday ETF entry signals here. No live fundamentals, news, order-flow or economic-calendar API is available in this script. The explicit fundamental control is a dated manual Bullish/Bearish/Neutral/No-trade bias based on information YOU review. With the gate enabled, an expired/missing interval blocks new entries instead of silently applying stale bias. A separately dated manual event-blackout interval blocks overlapping candles. Both are off by default. Manual historical bias can introduce hindsight and is not a validated fundamental backtest. No automated fundamentals feed is claimed.

## Installation and verification

Disable old alerts separately, remove old chart version, replace ALL Pine Editor contents with PRECISION_TREND_BOXES_v27.txt, save and add on standard SPY/QQQ5m. On a confirmed accepted cross, inspect the exact entrybar and all four prices. Compare against Strategy Tester order details; commission0.01% and one-tick slippage are configured, so SIGNAL ENTRY can differ from Tester fill. Use standard candles, not synthetic candle fills.

Strategy Tester uses100 underlying shares by default, half exited at each bracket. CALL means long underlying direction; PUT means short underlying direction. The reference ATM strike and5-contract display do not select, quote, buy or sell actual options. No Webull service was changed or order sent. Do not point the broker webhook at these plain-text alerts. The five-contract receiver work from earlier remains separate and undeployed.

Completed backtest results depend on TradingView's broker emulator, available intrabar data, costs, bar history and enabled filters. A drawing is not fill confirmation. Native TradingView compile and replay are still required: source declaration, delimiter, drawing-allocation, same-evaluation bracket and bounded-history checks passed locally; no Pine compiler or market replay was available here. No profitability claim.
