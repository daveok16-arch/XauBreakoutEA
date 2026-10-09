import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import strategy
from frequency_bridge import run
from dataclasses import replace


def synthetic(n=800, seed=1):
    """A mildly trending random walk with OHLC - enough to exercise the engine."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.3, 5.0, n).cumsum() + 2000.0
    close = np.abs(steps)
    high = close + np.abs(rng.normal(0, 2, n))
    low = close - np.abs(rng.normal(0, 2, n))
    open_ = close + rng.normal(0, 1, n)
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": 0}, index=idx)


class TestFrequencyBridge(unittest.TestCase):
    def test_run_returns_expected_fields(self):
        df = synthetic()
        p = replace(strategy.Params(), allow_short=False, lookback=20)
        x = run(df, p, "N=20")
        for k in ("n", "tpy", "win", "avgR", "pf", "dd", "cagr", "t", "chunks", "ann_ev"):
            self.assertIn(k, x)
        self.assertGreaterEqual(x["n"], 0)
        self.assertGreaterEqual(x["tpy"], 0.0)

    def test_annual_ev_identity(self):
        # annEV% = trades/yr * avgR * risk% (in percent)
        df = synthetic()
        p = replace(strategy.Params(), allow_short=False, lookback=20)
        x = run(df, p, "N=20")
        if x["n"] > 0:
            expected = x["tpy"] * x["avgR"] * (p.risk_pct / 100.0) * 100
            self.assertAlmostEqual(x["ann_ev"], expected, places=6)

    def test_shorter_lookback_trades_more(self):
        df = synthetic()
        a = run(df, replace(strategy.Params(), allow_short=False, lookback=5), "N=5")
        b = run(df, replace(strategy.Params(), allow_short=False, lookback=60), "N=60")
        self.assertGreaterEqual(a["n"], b["n"])


if __name__ == "__main__":
    unittest.main()
