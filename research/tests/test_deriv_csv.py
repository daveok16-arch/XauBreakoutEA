#!/usr/bin/env python3
"""Tests for the Deriv/MT5 CSV loader.

Run:  python3 -m unittest discover -s research/tests -v
 or:  python3 research/tests/test_deriv_csv.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # research/
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))  # project root

import deriv_csv  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class TestMTStyleTab(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(FIX, "deriv_mt5_tab.csv")
        self.df, self.rep = deriv_csv.load_csv(self.path)

    def test_row_count(self):
        self.assertEqual(self.rep.rows_in_file, 6)
        self.assertEqual(self.rep.rows_kept, 6)
        self.assertEqual(len(self.df), 6)

    def test_columns_and_ohlc_values(self):
        self.assertEqual(list(self.df.columns), ["Open", "High", "Low", "Close", "Volume"])
        first = self.df.iloc[0]
        self.assertAlmostEqual(first["Open"], 2062.10)
        self.assertAlmostEqual(first["High"], 2065.40)
        self.assertAlmostEqual(first["Low"], 2061.00)
        self.assertAlmostEqual(first["Close"], 2064.20)
        self.assertAlmostEqual(first["Volume"], 1200.0)   # from <TICKVOL>

    def test_timeframe_inferred_h1(self):
        self.assertEqual(self.rep.inferred_tf, "H1")

    def test_gap_flagged_not_filled(self):
        # 03:00 -> 05:00 is a one-bar hole; must be flagged, not invented.
        self.assertEqual(len(self.rep.gaps), 1)
        self.assertEqual(self.rep.gaps[0]["missing_bars"], 1)
        self.assertNotIn(pd.Timestamp("2024-01-02 04:00:00"), self.df.index)

    def test_tz_naive_convention(self):
        self.assertIsNone(self.df.index.tz)
        self.assertEqual(self.rep.timezone_convention,
                         "naive-UTC (raw wall clock, no offset applied)")

    def test_raw_file_untouched(self):
        self.assertEqual(self.rep.duplicate_timestamps, 0)


class TestSemicolonPrefixed(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(FIX, "deriv_semicolon_prefixed.csv")
        self.df, self.rep = deriv_csv.load_csv(self.path)

    def test_parsed(self):
        self.assertEqual(len(self.df), 3)
        self.assertAlmostEqual(self.df.iloc[0]["Open"], 2110.00)
        self.assertAlmostEqual(self.df.iloc[2]["Close"], 2116.50)
        self.assertAlmostEqual(self.df.iloc[0]["Volume"], 700.0)

    def test_timeframe_h1(self):
        self.assertEqual(self.rep.inferred_tf, "H1")


class TestDirtyFile(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(FIX, "deriv_dirty.csv")
        self.df, self.rep = deriv_csv.load_csv(self.path)

    def test_counts(self):
        self.assertEqual(self.rep.duplicate_timestamps, 1)
        self.assertEqual(self.rep.malformed_rows, 1)        # 'bad' close
        self.assertEqual(self.rep.ohlc_inconsistent, 1)     # high < open
        self.assertEqual(self.rep.nonpositive_prices, 1)    # open = 0
        self.assertEqual(self.rep.rows_kept, 3)

    def test_kept_rows_are_the_valid_ones(self):
        self.assertEqual(
            [str(t) for t in self.df.index],
            ["2024-05-01 10:00:00", "2024-05-01 11:00:00", "2024-05-01 15:00:00"],
        )

    def test_gap_after_dropping(self):
        # 11:00 -> 15:00 leaves a 3-bar hole once the bad rows are removed.
        self.assertEqual(len(self.rep.gaps), 1)
        self.assertEqual(self.rep.gaps[0]["missing_bars"], 3)

    def test_duplicate_kept_first(self):
        # the surviving 11:00 row is the first occurrence (close 2307.00)
        self.assertAlmostEqual(self.df.loc[pd.Timestamp("2024-05-01 11:00:00"), "Close"], 2307.00)


class TestOrderingAndDedup(unittest.TestCase):
    def test_sorts_ascending(self):
        import tempfile
        body = (
            "Date,Time,Open,High,Low,Close\n"
            "2024.06.03,02:00:00,10,12,9,11\n"
            "2024.06.03,00:00:00,8,10,7,9\n"
            "2024.06.03,01:00:00,9,11,8,10\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(body)
            p = fh.name
        try:
            df, rep = deriv_csv.load_csv(p)
            self.assertTrue(df.index.is_monotonic_increasing)
            self.assertEqual(str(df.index[0]), "2024-06-03 00:00:00")
            self.assertEqual(len(df), 3)
        finally:
            os.unlink(p)


class TestErrors(unittest.TestCase):
    def test_missing_ohlc_column_raises(self):
        import tempfile
        body = "Date,Time,Open,High,Close\n2024.06.03,00:00:00,8,10,9\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(body)
            p = fh.name
        try:
            with self.assertRaises(ValueError):
                deriv_csv.load_csv(p)
        finally:
            os.unlink(p)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            deriv_csv.load_csv(os.path.join(FIX, "nope.csv"))


class TestRawPreserved(unittest.TestCase):
    def test_file_hash_unchanged(self):
        path = os.path.join(FIX, "deriv_mt5_tab.csv")
        before = _sha(path)
        deriv_csv.load_csv(path)
        self.assertEqual(before, _sha(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
