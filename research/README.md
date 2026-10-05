# research/ — Python validation harness

Validates the *idea* behind XauBreakoutEA on real gold data, on Linux, without
MetaTrader. Uses COMEX gold futures (`GC=F`) as an XAUUSD proxy.

| File | Purpose |
|---|---|
| `fetch_data.py` | download + cache daily / H1 / 5m gold bars |
| `strategy.py` | indicators + bar-by-bar backtest engine + metrics |
| `walkforward.py` | out-of-sample validation (the result that matters) |
| `robustness.py` | parameter sensitivity, cost stress, bootstrap Monte Carlo |
| `signals_scan.py` | scan MQL5 Signals, recompute DD/CAGR, flag traps |
| `SIGNALS.md` | signals analysis findings |
| `deriv_csv.py` | Deriv/MT5 CSV loader (strict, tz-explicit, gap-flagging) |
| `preflight.py` | cheap pre-check before the expensive experiment |
| `deriv_fetch.py` | Deriv API data source (probe depth / fetch H1) |
| `STATUS.md` | where the project stands: proven / unproven / blocked |
| `validate_import.py` | import validation gate (self-consistency + overlap) |
| `compare_instruments.py` | spot-vs-futures diagnostic (never affects gates) |
| `long_history.py` | long-history H1/H4 study with a production gate |
| `DERIV_IMPORT.md` | how to export/import/validate a Deriv CSV |
| `tests/` | loader tests + fixtures |
| `portfolio.py` | multi-timeframe legs under a shared risk budget |
| `h4.py` | higher-timeframe leg (no look-ahead, realistic fills) |
| `PORTFOLIO.md` | shared-risk + overlap findings |
| `trailing_tp_ab.py` | controlled A/B: fixed TP vs trailing TP |
| `TRAILING_TP.md` | trailing-TP findings (negative result) |
| `gold_reaper_analysis.py` | reverse-engineer Gold Reaper sizing from its curve |
| `FINDINGS.md` | backtest conclusions |
| `data/`, `reports/` | generated output, not source |

```
python3 research/fetch_data.py --intraday
python3 research/strategy.py    --tf daily
python3 research/walkforward.py --tf daily
python3 research/robustness.py  --tf daily
```

Requires: pandas, numpy, matplotlib, yfinance.
