# v22 changes and validation limits

This revision keeps the complete visual build and JSON compatibility with the
existing sandbox worker (`amd_sweep_v1`). It does not require a backend update.
Sandbox alerts still default OFF and no credential is embedded.

## Concrete corrections

1. Removed the retest candle's relative-volume requirement. Displacement still
   requires volume confirmation; a quieter retest no longer fails that same test.
2. The default map includes intraday intermediate swings rather than restricting
   every level to outside premarket. Confirmed ordinary pivots and the frozen
   opening range can supply fallbacks. The stricter premarket-only mode remains
   an explicit optional input.
3. Already-taken levels are excluded from selection. A pierced level without a
   qualifying reclaim is consumed too, instead of being reused later as a fresh
   grab. Confirmation times remain causal and are not backdated.
4. Retests may penetrate the broken level while holding above/below the sweep
   extreme and closing back through structure. The old narrow symmetric wick
   band could reject otherwise valid reclaim/retest sequences.
5. Targets are placed just before the nearest recorded opposing liquidity,
   limited to the maximum configured R. When no opposing level is mapped, a
   target uses the configured fallback R and is labeled as such. Missing target
   data no longer automatically rejects the entry. A known barrier too close
   for the minimum R still rejects it by default.
6. Initial stops remain beyond the sweep wick, with a minimum sweep-ATR distance
   to avoid arbitrarily tiny risk boxes. The target's actual R is shown instead
   of always displaying a fixed 2R while using a different destination.
7. The optional heuristic score gate defaults OFF; the causal price sequence
   remains mandatory. No score has been calibrated into a success probability.
8. Dashboard status now distinguishes cutoff, session, lunch, daily limit,
   cooldown, missing data, displacement and retest waits. It shows the last
   rejection, selected liquidity levels and target basis.
9. A separate modeled-SPY results panel counts closed tracked signals and their
   modeled R. It is NOT actual fills, options profit or a profitability backtest;
   it excludes spreads, fees, time decay and volatility effects.
10. The cutoff uses bar CLOSE time to match the worker's 14:00 New York cutoff.
    A 13:55–14:00 candle cannot emit a new entry exactly at the server cutoff.

These changes can increase signal frequency and change risk. That is not evidence
of improved returns. Entries still require a sweep/reclaim, later displacement
and later retest. A continuing move without that sequence will produce no entry.
After the cutoff, no new trades are eligible. The decorative volume cells remain
explicitly estimated OHLCV data, not real aggressor order flow.

## Checked versus unverified

Checked the source for one declaration, balanced delimiters, expected output
components, JSON compatibility, and six independent numerical stop/target
scenarios (CALL/PUT with known, unknown and obstructed target space).

This is not native Pine compilation. TradingView compilation, historical replay,
live alert behavior, options outcomes and profitability remain unverified.

## Install without mixing scripts

Stop the old alert before replacing the indicator. Download the .txt file, open
it in Notepad, copy the entire file, then Ctrl+A in Pine Editor and replace the
entire contents. Save as SPY OPTIONS FULL v22 and add it to a standard SPY
5-minute chart. Review the new defaults; old saved input overrides may persist
if you reuse an existing script instance.

Leave sandbox alerts OFF during compilation and replay. Re-enter the current
private token only when you intentionally configure paper validation, then
create a fresh Any alert() function call alert using the existing webhook URL.
Changing the chart's code does not update an already-created TradingView alert.
