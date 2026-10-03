#!/usr/bin/env python3
"""
Fetch and cache gold price data for strategy research.

XAUUSD itself is a broker-synthetic spot pair and has no free public tick feed,
so we use COMEX gold futures (GC=F) as a proxy. It tracks spot gold closely and
is the best freely available history. Data is cached to CSV under research/data/.

Usage:
    python3 research/fetch_data.py             # daily + hourly
    python3 research/fetch_data.py --intraday  # also 5m (60-day window)
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SYMBOL = "GC=F"

SPECS = {
    "daily": {"period": "max", "interval": "1d"},
    "h1": {"period": "730d", "interval": "1h"},
    "m5": {"period": "60d", "interval": "5m"},
}


def fetch(name: str) -> pd.DataFrame:
    spec = SPECS[name]
    df = yf.download(
        SYMBOL,
        period=spec["period"],
        interval=spec["interval"],
        progress=False,
        auto_adjust=False,
    )
    if df is None or len(df) == 0:
        raise RuntimeError(f"no data returned for {SYMBOL} {name}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index.name = "datetime"
    return df


def load(name: str) -> pd.DataFrame:
    """Load a cached series, fetching it first if necessary."""
    path = os.path.join(DATA_DIR, f"{SYMBOL.replace('=', '_')}_{name}.csv")
    if not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        df = fetch(name)
        df.to_csv(path)
        return _normalize_index(df)
    df = pd.read_csv(path, index_col=0)
    return _normalize_index(df)


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce the index to tz-naive timestamps (intraday files carry offsets)."""
    idx = pd.to_datetime(df.index, utc=True, errors="coerce")
    df.index = idx.tz_convert(None)
    df = df[~df.index.isna()].sort_index()
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--intraday", action="store_true", help="also fetch 5m bars")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    names = ["daily", "h1"] + (["m5"] if args.intraday else [])

    for name in names:
        df = fetch(name)
        path = os.path.join(DATA_DIR, f"{SYMBOL.replace('=', '_')}_{name}.csv")
        df.to_csv(path)
        print(
            f"{name:6s} {len(df):7d} bars  {df.index.min()} -> {df.index.max()}  -> {path}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
