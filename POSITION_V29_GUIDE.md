# v29 — screenshot-style position frames

The supplied screenshot shows TradingView native Long/Short Position drawings. Pine can draw equivalent joined green/red risk/reward boxes, centered summary and edge labels. Scripts cannot create the native interactive drawings or their blue drag handles. The screenshot's hindsight entry placement and profits are not evidence that an algorithm could have identified those trades prospectively.

## Fixed chart compatibility and presentation

v28 explicitly rejected every timeframe except1m. The new screenshot is5m, so that guard alone could stop the old script. v29 accepts standard SPY1m OR5m; signals follow the selected chart's actual bars. A5m chart does not secretly execute1m confirmations. Confirmed pivot right-bars are2by default (10minutes confirmation lag on5m); no marker is backdated.

Joined green reward/red risk frame. Target and stop labels centered at the outer edges show exact underlying prices, points and percentages. Entry and R:R summary is centered on the shared boundary. A gray dashed line connects entry to current/exit underlying reference. Completed frames freeze at the exit candle, and their summary explicitly says SPY modeled points, not option P&L or broker fill. Cash Amount/Qty inferred from a hypothetical account is deliberately absent;5option contracts and nearest ATM strike remain reference only. Gaps through stops use the worse open in the modeled point result. If stop and target both touch the same candle, stop takes conservative precedence.

Optional TP1/TP2, EMA/VWAP lines, stage markers and horizontal levels are off by default to match the clean screenshot. They remain available in Settings. The dashboard retains prior-day high/low/close, premarket high/low, completed5m/30m/4h trend, relative volume, yield change and sector participation proxy.

## Exact entry/stop/target rules

CALL: wick through and reclaim a known support/low (or previous-close reclaim from below), then bullish displacement through the frozen prior confirmed swing high. Entry at that displacement close in Breakout or Retest mode; alternatively a held retest above the break. PUT: rejection of known resistance/high, break below frozen prior confirmed swing low, then bearish break entry or failed-rebound retest. Default VWAP alignment remains required. Invalidation beyond the arming wick or expiry cancels the setup. No prediction of resting liquidity or absorption is made from candles.

SL beyond invalidating wick plus0.1ATR buffer, minimum0.5ATR distance; reject risk greater3ATR. Final TP before nearest known opposing level, minimum1.5R room; explicitly labeled2.5R fallback if none mapped, capped3R. Reject insufficient room rather than tightening stop to improve R:R. TP1/TP2 are advisory, not automatic partial broker sales. No price from the example screenshot is hard-coded.

## Fundamental information

Dated reviewed CPI/Fed/earnings/headline bias and event exclusion can block entries. Neither is a live calendar or news feed. Optional real yield-percent context uses TVC:US10Y if available, measuring the prior15-minute change in basis points. Sector ETF returns are a participation proxy, not actual market breadth or earnings surprises. Missing yield data blocks entries if its filter is enabled. No universally best profitable technical/fundamental combination is claimed, and no historical fundamental backtest is verified.

## Token, automation and installation

Token option retained: Settings ->5 — Optional PAPER webhook JSON ->Private WEBHOOK_TOKEN. Blank/off by default. Recreate alert after changing source or inputs. Routing URL belongs in alert Notifications; never share token. Protocol stays structure_v28 for compatibility with the prepared receiver adapter. Trade IDs useS29 + chart timeframe + close time. Only realtime paper entries inside the configured paper window emit JSON. Quantities/initial entry/stop/final target are frozen through exit. Receiver support must be verified before enabling.

Existing deployed receivers may not accept this protocol. The compatible receiver adapter remains prepared on the review branch, not deployed. Default paper entry09:45–13:55 and paper exit14:00NewYork remain independent of chart entries until15:50/chart exit15:55. Afternoon drawings are visual-only under that policy. No broker order or deployment was performed.

Remove the previous indicator instance, disable old alerts separately, replace ALL Pine Editor contents withSPY_POSITION_FRAMES_v29.txt, save, add onSPY5m. The complete file is456lines. Confirm no runtime-error icon; inspect entry anchors and labels on an accepted setup. Source structural checks passed (declaration, balanced delimiters,1m/5m guard, frame lifecycle and frozen JSON fields). Native TradingView compilation, rendering and market replay have not been verified here. Earlier31receiver mock tests do not validate Pine performance or option profitability.
