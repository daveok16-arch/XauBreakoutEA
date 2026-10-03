# XauBreakoutEA

A transparent XAUUSD breakout Expert Advisor for MetaTrader 5, plus a Python
research harness that validates the strategy on real gold data before a line of
it is trusted.

Built to be the opposite of a black-box market EA: no grid, no martingale, hard
stops on every position, and every claim reproducible.

## What's here

| Path | Purpose |
|---|---|
| `Experts/XauBreakoutEA/` | The MT5 Expert Advisor (MQL5) |
| `Include/RiskManager.mqh` | Percent-risk sizing, exposure and daily-loss guards |
| `Include/NewsGuard.mqh` | Economic-calendar blackout filter |
| `research/` | Python backtest, walk-forward and robustness harness |
| `DERIV_SETUP.md` | Deployment guide for Deriv MT5 |
| `AGENTS.md` | Project conventions and findings |

## The strategy

1. **Signal** - Donchian breakout of the prior N completed bars (default 60).
2. **Filter** - bar-close confirmation, session window, spread and news guard.
3. **Risk** - ATR-based stop (1.5 x ATR), take profit at 2R, position size
   derived from the actual stop distance at 0.75% of equity.
4. **Manage** - ATR trailing stop armed after 1R.

Entries are taken at the next bar's open on completed bars only, so there is no
intra-bar repaint.

## Validation

Measured on COMEX gold futures (`GC=F`) as an XAUUSD proxy, daily 2000-2026.

| Check | Result |
|---|---|
| Walk-forward, daily | 6/6 folds positive out-of-sample |
| Mean OOS profit factor | 1.79 |
| IS to OOS degradation | 3.4 pts (small = not curve-fit) |
| Cost stress | survives 3x spread + commission |
| Bootstrap Monte Carlo | prob(ending below start) 0.2% |

See `research/FINDINGS.md` for the full write-up and `research/README.md` to
reproduce it.

## Install

Copy `Include/*.mqh` to `MQL5/Include/` and `Experts/XauBreakoutEA/` to
`MQL5/Experts/XauBreakoutEA/`, then compile `XauBreakoutEA.mq5` in MetaEditor
(F7). See `DERIV_SETUP.md` for the Deriv-specific steps.

## Honest caveats

- The harness uses a futures proxy, not spot XAUUSD, and bar-level fidelity.
- The MQL5 code has not yet been validated in the MT5 Strategy Tester.
- A breakout edge of ~1.5 profit factor is what an honest gold system looks
  like. It is not a get-rich curve, and it is not sold as one.

## Licence

Use at your own risk. Nothing here is financial advice.
