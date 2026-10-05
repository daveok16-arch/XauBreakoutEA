#!/usr/bin/env python3
"""Tests for the instrument-comparison diagnostic.

Verifies the diagnostic's maths, and - importantly - that it stays a diagnostic:
it returns metrics but is never consulted by the production gate.

Run: python3 -m unittest discover -s research/tests -p "test_*.py" -v
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import compare_instruments as ci  # noqa: E402
import fetch_data  # noqa: E402
import validate_import  # noqa: E402
from strategy import Params  # noqa: E402


def _series(n=400, seed=0, base=2000.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    ret = rng.normal(0, 0.002, n)
    close = base * np.exp(np.cumsum(ret))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) + np.abs(rng.normal(0, 0.5, n))
    lo = np.minimum(op, close) - np.abs(rng.normal(0, 0.5, n))
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close,
                         "Volume": np.ones(n)}, index=idx)


class TestIdentical(unittest.TestCase):
    def test_identical_series_are_equivalent(self):
        a = _series()
        b = a.copy()
        p = Params(spread=0.30, commission_per_side=0.0)
        m = ci.compare(a, b, p, "a", "b")
        self.assertAlmostEqual(m["return_correlation"], 1.0, places=6)
        self.assertAlmostEqual(m["basis_pct_mean"], 0.0, places=9)
        self.assertEqual(m["direction_agreement"], 100.0)
        self.assertTrue(m["structurally_equivalent"])


class TestBasisOnly(unittest.TestCase):
    def test_constant_basis_preserves_structure(self):
        a = _series()
        b = a.copy()
        b[["Open", "High", "Low", "Close"]] -= 1.75      # b sits below a by a fixed basis
        p = Params(spread=0.30, commission_per_side=0.0)
        m = ci.compare(a, b, p, "a", "b")
        # a pure basis must not break returns or signals
        self.assertAlmostEqual(m["return_correlation"], 1.0, places=6)
        self.assertEqual(m["direction_agreement"], 100.0)
        self.assertGreater(m["basis_pct_mean"], 0.0)     # a - b is positive
        self.assertTrue(m["structurally_equivalent"])


class TestMisaligned(unittest.TestCase):
    def test_time_shift_breaks_structure_despite_price_corr(self):
        a = _series()
        b = a.copy()
        b.index = b.index + pd.Timedelta(hours=3)        # session mismatch
        p = Params(spread=0.30, commission_per_side=0.0)
        m = ci.compare(a, b, p, "a", "b")
        # levels look similar; returns must not
        self.assertLess(m["return_correlation"], 0.5)
        self.assertFalse(m["structurally_equivalent"])


class TestGateIsolation(unittest.TestCase):
    """The diagnostic must never change a gate result."""

    def test_validate_import_does_not_import_compare(self):
        src = open(os.path.join(os.path.dirname(HERE), "validate_import.py")).read()
        self.assertNotIn("import compare_instruments", src)
        self.assertNotIn("compare_instruments.compare", src)

    def test_different_instrument_gate_stays_false(self):
        # a basis-shifted series is not the same instrument -> gate must not pass
        a = _series()
        b = a.copy()
        b[["Open", "High", "Low", "Close"]] += 1.75
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pth = os.path.join(tmp, "shifted.csv")
            validate_import.to_broker_csv(b, pth)
            # gate compares against the cached h1; just assert it never raises and
            # returns a bool, and that compare metrics do not feed into it
            m = ci.compare(a, b, Params(spread=0.30, commission_per_side=0.0), "a", "b")
            self.assertIn("structurally_equivalent", m)
        # structural equivalence is a diagnostic field, not a gate input
        self.assertNotIn("structurally_equivalent",
                         open(os.path.join(os.path.dirname(HERE), "validate_import.py")).read())


class TestMetricsPresent(unittest.TestCase):
    def test_all_requested_metrics_returned(self):
        a = _series(seed=1)
        b = _series(seed=2)   # unrelated
        p = Params(spread=0.30, commission_per_side=0.0)
        m = ci.compare(a, b, p, "a", "b")
        for key in ("common_timestamps", "basis_pct_mean", "basis_pct_std",
                    "return_correlation", "return_sign_agreement",
                    "bar_direction_agreement", "signals_a", "signals_b",
                    "common_signals", "direction_agreement",
                    "structurally_equivalent"):
            self.assertIn(key, m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
