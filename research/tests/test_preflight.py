#!/usr/bin/env python3
"""Tests for the preflight gate (exit codes and hard/soft checks)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import preflight  # noqa: E402
import validate_import  # noqa: E402


def _write(series: pd.DataFrame, path: str):
    validate_import.to_broker_csv(series, path)


def _h1_series(start, end):
    idx = pd.date_range(start, end, freq="1h")
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(3)
    close = 1500 * np.exp(np.cumsum(rng.normal(0, 0.001, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) + 0.4,
                         "Low": np.minimum(op, close) - 0.4, "Close": close}, index=idx)


def _run(argv):
    old = sys.argv
    sys.argv = ["preflight.py"] + argv
    try:
        return preflight.main()
    finally:
        sys.argv = old


class TestPreflight(unittest.TestCase):
    def test_short_history_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "short.csv")
            _write(_h1_series("2024-01-01", "2026-01-01"), p)
            self.assertEqual(_run(["--csv", p]), 1)

    def test_long_history_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "long.csv")
            _write(_h1_series("2012-01-01", "2025-01-01"), p)
            self.assertEqual(_run(["--csv", p]), 0)

    def test_min_years_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "short.csv")
            _write(_h1_series("2024-01-01", "2026-01-01"), p)
            self.assertEqual(_run(["--csv", p, "--min-years", "1"]), 0)

    def test_wrong_timeframe_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "daily.csv")
            idx = pd.date_range("2010-01-01", "2025-01-01", freq="1D")
            s = pd.DataFrame({"Open": 1.0, "High": 1.1, "Low": 0.9, "Close": 1.0},
                             index=idx)
            _write(s, p)
            self.assertEqual(_run(["--csv", p]), 1)

    def test_unloadable_file_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "junk.csv")
            with open(p, "w") as fh:
                fh.write("not,a,valid,export\n1,2,3\n")
            self.assertEqual(_run(["--csv", p]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
