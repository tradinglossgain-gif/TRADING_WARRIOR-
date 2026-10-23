# Scalp Lab v30 — separate two-day Strategy Tester build

This is a NEW strategy script. No existing chart indicator, alert, source file or broker service has been removed, hidden or modified. Use Pine Editor -> New strategy, not an existing script buffer. Only add the new strategy; do not choose Replace or remove existing indicators.

## Test window and outputs

Default latest2calendar dates, anchored to the latest loaded chart bar in New York time. This is not always2trading sessions (weekends/holidays may reduce coverage); the dashboard explicitly counts actual session dates with loaded bars. Custom start/end timestamps are available. Earlier bars warm up indicators; order creation is blocked outside the selected window. Custom end handling closes an existing position on the first available bar outside the window if it remains open; that exit may be later than the boundary at chart resolution. An unfinished current-window position is displayed separately as open P/L, not fabricated as a closed win.

Strategy Tester and the bottom dashboard use TradingView's broker-emulator values: net P/L, gross-profit/gross-loss profit factor, realized exit win percentage, maximum drawdown and open P/L.50/50 exits generate separate exit records; labels explicitly say EXIT RECORDS rather than implying complete round trips. Zero trades/zero losses display zero orN/A rather than inventing results. These are implemented calculations, not precomputed performance results.

Defaults:100underlying shares,100,000initial capital,0.01%commission per order and1tick slippage. Not an options backtest. CALL means underlying long direction and PUT underlying short direction. Option strike/5contract display elsewhere is reference only. Actual option spreads, fills, premium decay, volatility and exercise behavior are not modeled. Costs can be changed in Strategy Properties; labels identify source defaults. Same-bar fill order follows TradingView broker emulator; Bar Magnifier can be evaluated if the user's plan/data supports it. It is not enabled or verified here.

## Entry, stop, target and drawing rules

Selectable EMA10/20 cross, trend pullback, or Both(default). Close-confirmed only; optional confluence is on by default: VWAP alignment, DMI/ADX18, relative volume0.8, RSI direction with overextension bounds. Completed15m EMA20 confirmation is available but off by default. No future prices determine entries. No source configuration has been optimized against the unobserved last2days.

Structure stop is beyond the recent3bar extreme plus0.1ATR buffer, or minimum1.2ATR distance, whichever is farther. TP1=1R andTP2=2R. The strategy reserves half the original fixed share quantity for each protective bracket on the entry calculation. Daily cutoff15:55NewYork and session09:30–16:00; maximum6entries/day. Opposite confirmed cross can reverse when selected criteria pass. Position sizing is rejected if modeled equity would not support the configured underlying quantity.

Joined green/red frames, exact SL/TP labels on outer edges and centered signal-entry/R:R summary. Retained completed frames default16. Signal entry uses the confirmed close and can differ from Tester average fill due to slippage. Dashboard shows actual average model fill. Completed status comes from Tester trade records, not a guessed profitable arrow. No fake order-flow/footprint or live-fundamental data is added. Dated manual macro/event exclusions remain explicitly manual and off by default.

## Install without deleting any indicators

1. OnSPY5m, open Pine Editor -> create a NEW strategy.
2. Paste the entireSPY_SCALP_BACKTEST_v30.txt source and save under its own name.
3. ClickAdd to chart. Leave every existing indicator and old script untouched.
4. OpenStrategy Tester -> Overview andList of trades. The source defaults to the latest2calendar dates; inspect actual sessions loaded in the bottom panel.
5. Adjust date range and explicit inputs rather than selecting only favorable arrows. Inspect losing trades, costs, zero-signal sessions and out-of-sample dates. Two days is a short functional check, not proof of a profitable edge.

## Execution boundaries and verification

Broker JSON is absent. Strategy order alerts are explicitly suppressed; optional plain-text signal alerts are off by default. This build does not alter existing alerts, connect Webull or place broker orders. Existing alerts remain independent and can still run.

Source checks passed: one strategy declaration, date gate, prior-bar indicator warmup, explicit costs, disabled order alerts, fixed exit quantities, bounded drawings and balanced delimiters. The complete source is328lines. No native TradingView compiler, browser-control tool, or historical SPY feed is accessible in this session; actual compilation, two-day performance, chart rendering and deployment are UNVERIFIED. The visible chart URL is not an authenticated browser-control connection. No claim that this is already applied or profitable.
