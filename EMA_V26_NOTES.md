# v26 chart indicator

Purpose: visibly draw an entry/risk/reward frame on every confirmed fast/slow EMA cross. Fast/slow default10/15. The Hull color change in earlier indicators is a different signal.

v25 required a selected entry engine, candle alignment, target room, stop distance, session/lunch window, cooldown, daily limit and no active trade. Its 14:00 cutoff was visible in the supplied screenshot. v26 has no such entry gates. The optional 09:30–16:00 regular-hours restriction is off by default. After ATR warmup, a confirmed EMA cross creates two boxes, three exact-price lines and three labels. Values are also printed inside the boxes and persistent dashboard. Historical frames are retained (six by default, configurable1–20).

Entry is crossover-bar close, never a selected earlier candle. Stop is the recent three-bar extreme plus0.1ATR buffer, with minimum0.5ATR risk distance. Target is2R by default. Levels remain frozen. Latest modeled trade ends on stop/target touch or a new opposite cross. Evaluation starts AFTER entry bar; if both levels touch on one later bar, label explicitly says SL(BOTH TOUCHED), since OHLC does not establish order. Frames do not establish fills or option performance.

Market context: EMA50/VWAP position, relative volume, prior completed15m/60m EMA20 bias. These are descriptions of SPY, not real order flow or comprehensive market internals. Their values do not gate entries.

Automation: none in this chart-focused version. Five contracts and rounded ATM strike are displayed references only. Alertconditions provide chart notifications; never attach the Webull order webhook to these plain-text alerts. Existing alerts remain independent and must be disabled separately. Existing v25 receiver bundle is preserved; no deployment has changed.

Installation: disable old alerts; remove the old indicator from the chart; replace ALL Pine Editor contents, save, add v26 on SPY5m. Verify both a bullish and bearish historical cross produce frames anchored at actual cross close. Existing alerts do not inherit new script source.

Verification: source structural and drawing-allocation checks passed. Native TradingView compilation, actual chart rendering and market-data replay remain unverified here. No broker order was submitted and no profitability is claimed.
