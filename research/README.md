# research/ — Python validation harness

Validates the *idea* behind XauBreakoutEA on real gold data, on Linux, without
MetaTrader. Uses COMEX gold futures (`GC=F`) as an XAUUSD proxy.

| File | Purpose |
|---|---|
| `fetch_data.py` | download + cache daily / H1 / 5m gold bars |
| `strategy.py` | indicators + bar-by-bar backtest engine + metrics |
| `walkforward.py` | out-of-sample validation (the result that matters) |
| `robustness.py` | parameter sensitivity, cost stress, bootstrap Monte Carlo |
| `FINDINGS.md` | written conclusions |
| `data/`, `reports/` | generated output, not source |

```
python3 research/fetch_data.py --intraday
python3 research/strategy.py    --tf daily
python3 research/walkforward.py --tf daily
python3 research/robustness.py  --tf daily
```

Requires: pandas, numpy, matplotlib, yfinance.
