# Multi-timeframe portfolio: shared risk budget and overlap

Follow-up to the trailing-TP study. The trailing TP failed because it changed the
exit, not the edge. Gold Reaper's other documented differentiator is running
**multiple timeframes at once**. This tests whether adding a higher-timeframe leg
to the same breakout edge helps - and, crucially, whether it helps for real or
only by double-counting the same trend.

Reproduce with `python3 research/portfolio.py`.

## Why the legs are not independent

Both legs trade the same breakout of the same gold trend, so they are correlated
by construction. Two consequences drive the whole design:

1. A shared risk budget must cap the **combined** open risk. Two legs that each
   take 0.75% are not "0.75% each" in portfolio terms if they fire together.
2. Overlap must be measured, not assumed. If the higher-timeframe leg enters the
   same trend the lower-timeframe leg is already in, the second entry adds risk
   without adding a new bet.

## Realistic timing and costs

- The higher timeframe is resampled from the lower one and labelled by **close**
  time, so a signal only uses candles that have completed.
- The entry is placed at the **first lower-timeframe open at or after the HTF
  close** - the earliest realistic fill, never before the signal existed.
- Both legs pay half-spread + commission on entry and exit, identical to the
  rest of the harness.

## Variants (identical data, costs and risk)

1. lower timeframe only (production leg)
2. higher timeframe only (new leg)
3. combined, **one shared risk budget**
4. combined, one budget per leg (the naive, risk-doubling case)

The only difference between 3 and 4 is the budget rule.

## Result 1: H1 + H4 (recent window, 2024-05 .. 2026-10)

| Variant | Trades | CAGR | Net | Max DD | PF | Win/loss |
|---|---|---|---|---|---|---|
| H1 only | 439 | 24.9% | 70.4% | 10.5% | 1.38 | 1.65 |
| H4 only | 124 | 12.7% | 33.3% | 4.9% | **1.76** | 1.82 |
| combined, shared | 563 | 40.1% | 124.3% | 10.6% | 1.46 | 1.69 |
| combined, independent | 563 | 40.1% | 124.3% | 10.6% | 1.46 | 1.69 |

Overlap: **253 overlapping H1/H4 pairs, 251 (99.2%) in the same direction.**

Three things to note:

- The **H4 leg is higher quality per trade** (PF 1.76 vs 1.38, DD 4.9% vs 10.5%)
  but trades less often, so its total return is lower.
- The **combined return (40.1%) exceeds either leg**, and max drawdown is not
  worse than H1 alone - both legs' worst drawdowns land in the same early window,
  and H1 dominates the percentage.
- **Variants 3 and 4 are identical.** With two legs at 0.75% each, combined open
  risk peaks at 1.5%, below the 3% cap, so the shared budget never binds. The
  budget only matters if you tighten it:

| max total risk | CAGR | Max DD | PF | Trades |
|---|---|---|---|---|
| 0.75% | 24.4% | 8.7% | 1.37 | 427 |
| 1.00% | 31.8% | 9.0% | 1.43 | 563 |
| 1.50% | 40.1% | 10.6% | 1.46 | 563 |
| 2.00% | 40.1% | 10.6% | 1.46 | 563 |

At a 0.75% shared cap the combined portfolio behaves like a single position -
drawdown falls to 8.7%, and so does return. That is the honest trade-off.

## The problem with the H1/H4 result

The H1 series only starts in May 2024 - **2.4 years, and one long gold bull
run**. A 40% CAGR on a single regime is not evidence. So the same engine was run
on the **26-year daily series with a weekly leg**, which spans bull, bear, chop
and two crises.

## Result 2: Daily + weekly (2000-08 .. 2026-10, 26 years)

| Variant | Trades | CAGR | Net | Max DD | PF | Win/loss |
|---|---|---|---|---|---|---|
| daily only | 267 | 1.7% | 57.0% | 12.1% | 1.55 | 1.81 |
| weekly only | 53 | 0.8% | 23.1% | **6.2%** | **2.39** | 1.83 |
| combined, shared | 320 | **2.5%** | **92.0%** | **10.8%** | **1.66** | 1.82 |
| combined, independent | 320 | 2.5% | 92.0% | 10.8% | 1.66 | 1.82 |

Overlap: **134 pairs, 133 (99.3%) same direction** - the same double-counting
signature as H1/H4.

This one holds up better:

- The combined portfolio **beats both legs** on CAGR, net return, profit factor
  and drawdown. Adding the weekly leg improves PF from 1.55 to 1.66 and *cuts*
  max drawdown from 12.1% to 10.8%.
- The weekly leg alone has the best quality (PF 2.39, DD 6.2%) - it is a slow,
  high-conviction filter, exactly what a higher timeframe should be.

### Out-of-sample segments (fixed parameters)

| Segment | daily | weekly | combined |
|---|---|---|---|
| 1 (2000-2005) | -1.8% | 4.6% | **2.6%** |
| 2 (2005-2009) | 9.5% | 7.9% | 17.9% |
| 3 (2009-2013) | 5.7% | 5.4% | 11.3% |
| 4 (2013-2018) | 7.0% | -3.1% | 3.7% |
| 5 (2018-2022) | 14.4% | 2.3% | 17.0% |
| 6 (2022-2026) | 13.7% | 5.1% | 19.3% |
| **mean** | 8.1% | 3.7% | **12.0%** |
| **positive** | 5/6 | 5/6 | **6/6** |

The combined portfolio is the only variant positive in **every** segment, and it
improves the mean. Crucially, in the two segments where the daily leg is weak
(seg 1, -1.8%) or the weekly leg is negative (seg 4, -3.1%), the other leg
carries it. That is real diversification between *different resolutions of the
same edge*, not merely leverage.

## Honest read

- **The H4 result is not trustworthy.** 2.4 years, one regime, and the legs are
  99% same-direction correlated. Treat the 40% CAGR as unproven.
- **The daily/weekly result is the credible one.** 26 years, 6 regimes, positive
  in all of them, and it improves return *and* drawdown together. That is the
  signature of genuine diversification rather than risk-stacking.
- **Both results share the same caveat**: 99% same-direction overlap. The higher
  timeframe is not adding a new bet; it is a slower, higher-quality expression of
  the same breakout. The improvement comes from *quality* (the weekly leg's PF
  2.39) and from timing differences, not from independence.
- **The shared budget is currently non-binding** at 0.75% per leg. It becomes the
  binding constraint only if you tighten it, and tightening it trades return for
  drawdown roughly one-for-one.

## Decision on the production EA

**The production EA is unchanged.** Per the agreed plan, it stays as the
single-timeframe system until the combined approach demonstrates a *repeatable*
out-of-sample improvement.

The daily/weekly evidence is promising but not yet sufficient to change
production, for one reason: **the production EA's own timeframe is H1, and the
credible combined result is on daily/weekly, a different system.** To justify a
production change we would need the H1+HTF combination to hold up over a long
history, which the free data does not provide (H1 only goes back to 2024).

Recommended next step before touching production:

1. Obtain a longer H1 series (broker export from Deriv MT5, which has years of
   M1/H1 history) and re-run H1+H4 over 10+ years.
2. If the combined edge survives there, implement the HTF leg as a separate
   module in the EA behind a default-off input, with a shared risk cap, and
   re-validate in the MT5 Strategy Tester.

Until then, this stays research.
