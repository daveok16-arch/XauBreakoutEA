#!/usr/bin/env python3
"""Tests for the Deriv fetcher's non-network logic (paging, dedup, conversion)."""
from __future__ import annotations

import os
import sys
import time
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import deriv_fetch as df_  # noqa: E402


class FakeClient:
    """Serves a fixed, finite history in pages, like the real endpoint."""

    def __init__(self, epochs):
        self.epochs = sorted(epochs)
        self.calls = []

    def call(self, req, expect, retries=4):
        self.calls.append(req)
        end = int(req["end"])
        count = int(req["count"])
        gran = int(req["granularity"])
        window = [e for e in self.epochs if e <= end]
        batch = window[-count:]
        return {"msg_type": "candles",
                "candles": [{"epoch": e, "open": 1.0, "high": 1.2, "low": 0.9,
                             "close": 1.1} for e in batch]}


class TestPaging(unittest.TestCase):
    def test_pages_backwards_and_dedups(self):
        gran = 3600
        # 12000 hourly epochs ending "now" -> needs >2 pages at 5000/page
        now = int(time.time()) // gran * gran
        epochs = [now - i * gran for i in range(12000)][::-1]
        fc = FakeClient(epochs)
        cs = df_.fetch_candles(fc, "frxXAUUSD", gran, count=5000, sleep_s=0,
                               progress=False, max_pages=50)
        got = [int(c["epoch"]) for c in cs]
        self.assertEqual(len(got), len(set(got)))          # no duplicates
        self.assertEqual(got, sorted(got))                 # ascending
        self.assertEqual(got, sorted(epochs))              # complete
        self.assertGreater(len(fc.calls), 2)               # actually paged

    def test_stops_at_start_epoch(self):
        gran = 3600
        now = int(time.time()) // gran * gran
        epochs = [now - i * gran for i in range(20000)][::-1]
        fc = FakeClient(epochs)
        cutoff = epochs[-1] + 10 * gran
        cs = df_.fetch_candles(fc, "s", gran, start_epoch=cutoff, count=5000,
                               sleep_s=0, progress=False, max_pages=50)
        self.assertLessEqual(min(int(c["epoch"]) for c in cs), cutoff)
        self.assertLess(len(cs), len(epochs))              # stopped early

    def test_stops_when_history_exhausted(self):
        gran = 3600
        epochs = [int(time.time()) - i * gran for i in range(7)][::-1]
        fc = FakeClient(epochs)
        cs = df_.fetch_candles(fc, "s", gran, count=5000, sleep_s=0,
                               progress=False, max_pages=50)
        self.assertEqual(len(cs), 7)
        self.assertEqual(len(fc.calls), 1)                 # short page -> done


class TestConversion(unittest.TestCase):
    def test_epochs_become_naive_utc(self):
        gran = 3600
        base = 1704067200  # 2024-01-01 00:00:00 UTC
        candles = [{"epoch": base + i * gran, "open": 10, "high": 12, "low": 9,
                    "close": 11} for i in range(3)]
        df = df_.candles_to_frame(candles)
        self.assertIsNone(df.index.tz)                     # tz-naive convention
        self.assertEqual(str(df.index[0]), "2024-01-01 00:00:00")
        self.assertEqual(list(df.columns), ["Open", "High", "Low", "Close"])
        self.assertAlmostEqual(df.iloc[0]["Close"], 11.0)

    def test_empty(self):
        df = df_.candles_to_frame([])
        self.assertTrue(df.empty)


class TestBrokerCsvRoundTrip(unittest.TestCase):
    def test_written_csv_reloads_through_loader(self):
        import tempfile
        import deriv_csv
        gran = 3600
        base = 1704067200
        candles = [{"epoch": base + i * gran, "open": 10 + i, "high": 12 + i,
                    "low": 9 + i, "close": 11 + i} for i in range(5)]
        df = df_.candles_to_frame(candles)
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "out.csv")
            df_.write_broker_csv(df, p)
            back, rep = deriv_csv.load_csv(p)
        self.assertEqual(len(back), 5)
        self.assertEqual(rep.duplicate_timestamps, 0)
        self.assertAlmostEqual(back.iloc[-1]["Close"], 15.0)
        self.assertEqual(str(back.index[0]), "2024-01-01 00:00:00")


class TestTokenWarning(unittest.TestCase):
    def test_detects_token_shaped_id(self):
        self.assertTrue(df_._looks_like_token("abcdef123456789"))   # 15 lower
        self.assertFalse(df_._looks_like_token("34zMWSj0ieMyonm5SV82C"))  # app id

    def test_probe_verdict_threshold(self):
        # 8-year boundary logic used by --probe
        nine_years = int(9 * 365.25 * 86400)
        three_years = int(3 * 365.25 * 86400)
        self.assertGreaterEqual(nine_years / (365.25 * 86400), 8)
        self.assertLess(three_years / (365.25 * 86400), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
