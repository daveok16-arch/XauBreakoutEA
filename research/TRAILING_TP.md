# Trailing take-profit: controlled A/B result

Question: Gold Reaper's edge is a 2.65 reward:risk. Ours is ~1.8. Would adding a
trailing take-profit close that gap?

Answer: **No. On this data the trailing TP makes every metric worse.** It is
implemented, off by default, and not recommended. Reproduce with
`python3 research/trailing_tp_ab.py`.

## The specification tested

- **Activation**: once favourable excursion reaches `trail_tp_start_r` x R
  (R = initial stop distance, 1.5 x ATR).
- **On activation**: the fixed TP is disabled, and a profit-side level is set at
  `extreme - trail_tp_atr` x ATR (long) / `extreme + trail_tp_atr` x ATR (short).
- **Exit**: the level ratchets only toward profit; the trade closes when price
  retraces to it. The stop and trailing stop stay active underneath.
- **Scope**: exits only. No grid, no martingale, no change to position sizing,
  no re-entry, no adding.

## Controlled setup

Both modes run on the **identical** series, with identical costs, spread,
commission and risk:

| Setting | Value |
|---|---|
| Data | COMEX gold futures (GC=F), XAUUSD proxy |
| Spread | 0.30 (full) |
| Commission | 0.0 (Deriv gold) |
| Slippage | modelled as the half-spread paid on entry and exit |
| Risk per trade | 0.75% of equity |
| Stop | 1.5 x ATR |
| Fixed TP | 2.0 R |
| Trailing stop | on, 2.0 x ATR, from 1.0 R |
| Start equity | 10,000 |

The only difference is the exit rule. That is the point of a controlled test.

## Results

### Daily (2000-08-30 .. 2026-10-02, 6,548 bars)

| Metric | Fixed TP (baseline) | Trailing TP | Verdict |
|---|---|---|---|
| CAGR | **1.8%** | 1.0% | worse |
| Net return | **57.0%** | 30.3% | worse |
| Max equity drawdown | 12.1% | 12.3% | no better |
| Profit factor | **1.55** | 1.27 | worse |
| Avg win / avg loss | **1.81** | 1.03 | worse |
| Win rate | 46.1% | 55.4% | higher (but wins are tiny) |
| Trades | 267 | 327 | more churn |
| Avg bars held | 5.4 | 4.2 | exits earlier |
| Avg R | **0.25** | 0.13 | worse |
| Sharpe | 0.31 | 0.31 | no better |
| Exits | stop 174 / target 93 | stop 151 / trail_tp 153 / target 23 | - |

### H1 (2024-05-10 .. 2026-10-02, 13,732 bars)

| Metric | Fixed TP | Trailing TP | Verdict |
|---|---|---|---|
| CAGR | **25.0%** | 1.0% | much worse |
| Net return | **70.4%** | 2.4% | much worse |
| Max equity drawdown | **10.5%** | 18.0% | worse |
| Profit factor | **1.38** | 1.03 | worse |
| Avg win / avg loss | **1.65** | 0.86 | worse |

The H1 result is close to catastrophic: the trailing TP gives back almost the
entire edge and *raises* drawdown.

## Why it fails

The exit breakdown explains it. The fixed TP exits 93/267 trades at exactly 2R.
The trailing TP instead closes 153/327 trades on the trail, at an average well
below 2R, and only 23 reach the old target. It **converts high-R winners into
low-R winners**. The win rate rises (55% vs 46%) because trades that would have
reversed to a loss are closed slightly positive - but the winners that used to
pay 2R now pay roughly 1R, so the whole edge shrinks.

This is the classic result for a breakout system on daily gold bars: bar-level
retracements are wide relative to the ATR trail, so the trail is hit constantly
before the move continues. The idea that "let winners run" helps is only true if
the trend persists past the trail distance, and on this data it does not.

## Parameter surface (daily, no cherry-picking)

| start_r \ trail_atr | 0.5 | 1.0 | 1.5 | 2.0 |
|---|---|---|---|---|
| 0.5 | 2.0 / 1.54 | 0.3 / 1.12 | 0.2 / 1.08 | 0.7 / 1.26 |
| 1.0 | 2.4 / 1.58 | 1.0 / 1.27 | 0.5 / 1.16 | 0.9 / 1.30 |
| 1.5 | 1.8 / 1.53 | 1.1 / 1.33 | 0.8 / 1.25 | 1.1 / 1.36 |
| 2.0 | 1.8 / 1.55 | 1.8 / 1.55 | 1.8 / 1.55 | 1.8 / 1.55 |

(cells are CAGR% / profit factor)

Only one cell (start 1.0, trail 0.5) beats the baseline CAGR, at 2.4% vs 1.8%,
and that is a single point in a 16-cell grid with a tiny edge - exactly the kind
of result that is noise. The row where `start_r = 2.0` collapses to the baseline
because the trail never activates before the fixed 2R target is hit.

## Out-of-sample segments (fixed parameters)

Parameters were fixed a priori, so every segment is genuinely unseen:

| Segment | Fixed TP | Trailing TP |
|---|---|---|
| 1 (2000-2005) | -1.8% | -2.1% |
| 2 (2005-2009) | 10.5% | 12.1% |
| 3 (2009-2013) | 5.5% | 5.7% |
| 4 (2013-2018) | 9.5% | -0.6% |
| 5 (2018-2022) | 14.4% | 7.2% |
| 6 (2022-2026) | 12.0% | 9.3% |
| **mean** | **8.4%** | **5.3%** |
| positive | **5/6** | 4/6 |

The improvement does not persist out of sample - it reverses.

## Where Gold Reaper's 2.65 R:R actually comes from

A trailing TP is not the mechanism. A reward:risk sweep on the same data shows
the ratio is simply a **dial on the fixed target**, and widening it does not
improve profit factor:

| reward_risk | CAGR | max DD | PF | avg win/loss | win rate |
|---|---|---|---|---|---|
| 1.5 | 1.5% | 12.5% | 1.44 | 1.54 | 48.3% |
| 2.0 | 1.8% | 12.1% | 1.55 | 1.81 | 46.1% |
| 3.0 | 1.5% | 13.2% | 1.52 | 1.94 | 43.9% |
| 5.0 | 1.6% | 12.4% | 1.56 | 2.20 | 41.5% |

Raising the target to 5R lifts the win/loss ratio to 2.20 and leaves profit
factor flat, because the win rate falls to compensate. So Gold Reaper's higher
R:R most likely comes from a **structurally different exit** - its trailing TP
plus its multiple internal strategies and multi-timeframe entries - not from a
knob we can turn on a single Donchian system.

## Decision

- The trailing TP is implemented in both the Python engine (`use_trailing_tp`,
  default `False`) and the MQL5 EA (`InpUseTrailingTP`, default `false`), so the
  finding is reproducible and the option exists.
- It is **off by default in both**. Enabling it would reduce returns and raise
  drawdown on this strategy.
- The honest conclusion: our ~1.8 R:R is not a defect to be "fixed" by a
  trailing exit. Chasing Gold Reaper's 2.65 by changing the exit makes things
  worse. The gap, if it is real, lives in their multi-strategy/multi-timeframe
  construction, which is a much larger piece of work.
