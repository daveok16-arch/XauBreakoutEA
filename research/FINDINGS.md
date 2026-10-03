# XauBreakoutEA — research findings

Date: 2026-10-03
Data: COMEX gold futures (`GC=F`) as an XAUUSD proxy — daily 2000-2026,
H1 2024-2026. Spot XAUUSD has no free public tick feed, so futures stand in.
This is a research harness, not a tick-accurate MT5 replica.

## Base configuration

| Parameter | Value |
|---|---|
| lookback | 60 bars |
| stop | 1.5 × ATR(14) |
| take profit | 2.0 R |
| trailing | 2.0 × ATR, armed after 1.0 R |
| risk per trade | 0.75% of equity |
| costs | 0.30 spread + 0.07/side commission per oz |

## Headline results

| Metric | Daily (2000-2026) | H1 (2024-2026) |
|---|---|---|
| trades | 267 | 545 |
| win rate | ~44% | ~44% |
| profit factor | 1.53 | 1.27 |
| CAGR | ~1.6% | 21.7% |
| max drawdown | 12.5% | 11.5% |
| Sharpe (daily) | 0.39 | 0.26 |

## Walk-forward (the only result that counts)

Six sequential folds; parameters optimized in-sample, measured on the next
unseen window.

| | Daily | H1 |
|---|---|---|
| folds positive OOS | **6/6** | 5/6 |
| mean OOS return | 10.7% | 8.7% |
| mean OOS profit factor | 1.79 | 1.30 |
| IS→OOS degradation | 3.4 pts | 7.4 pts |

A small IS→OOS gap on daily data means the edge is not a curve-fit artifact.

## Robustness

- **Parameter sensitivity:** degrades smoothly. Lookback 40→80 keeps PF
  1.38→1.66. `stop_atr` is the sensitive knob (1.0 → 1.5×ATR drops return
  83.7%→53.1%); the optimum sits at the aggressive edge of the tested range,
  so treat wider stops as the honest default.
- **Cost stress:** survives 3× spread+commission (PF 1.53→1.37). The edge is
  not a cost artifact.
- **Bootstrap Monte Carlo (2,000 resamples):** median drawdown 6.5%, p99 16.4%,
  5th-percentile final equity +21%, probability of ending below start 0.2%.

## Honest caveats

1. **Futures ≠ spot XAUUSD.** Futures have their own session gaps and roll.
   Real broker spot has different spreads, swap, and weekend gaps.
2. **Bar data hides intra-bar paths.** The engine resolves stop-vs-target
   adversarially (stop first), which is conservative, but gaps and slippage
   are not fully modelled.
3. **No news filter in the harness yet** — the MQL5 EA has one; the Python
   model does not, so live behaviour should be equal or better on that axis.
4. **CAGR on daily is low** (~1.6% over 26 years) because risk is fixed at
   0.75% and the breakout edge is thin on daily bars. H1 shows the edge more
   clearly. Neither is a get-rich curve — and that is the point.
5. **One asset, one family of strategies.** No multi-asset or multi-regime
   evidence yet.

## Verdict

The breakout idea with ATR stops, percent-risk sizing, and no grid/martingale
shows a **real but modest, cost-resistant, out-of-sample-stable edge**. It is
plausible enough to justify the next step — implementing the same logic
faithfully in MQL5 and validating against real broker tick data in the MT5
Strategy Tester.

## Reproduce

```
python3 research/fetch_data.py --intraday
python3 research/strategy.py    --tf daily
python3 research/walkforward.py --tf daily
python3 research/robustness.py  --tf daily
```
