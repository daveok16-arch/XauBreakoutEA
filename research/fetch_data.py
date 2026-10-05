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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SYMBOL = "GC=F"

SPECS = {
    "daily": {"period": "max", "interval": "1d"},
    "h1": {"period": "730d", "interval": "1h"},
    "m5": {"period": "60d", "interval": "5m"},
}


def fetch(name: str) -> pd.DataFrame:
    import yfinance as yf   # only needed for downloads; the CSV path avoids it

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


def load(name: str, csv_path: str | None = None) -> pd.DataFrame:
    """Load a cached series, fetching it first if necessary.

    If `csv_path` is given, the series is loaded from that Deriv/MT5 export
    instead of the cache. The raw file is never modified; the normalised frame
    is returned in memory and is NOT written back to the cache, so the existing
    download path stays exactly as it was.
    """
    if csv_path:
        import deriv_csv
        df, report = deriv_csv.load_csv(csv_path)
        _LAST_REPORT.clear()
        _LAST_REPORT.update(report.as_dict())
        return df
    path = os.path.join(DATA_DIR, f"{SYMBOL.replace('=', '_')}_{name}.csv")
    if not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        df = fetch(name)
        df.to_csv(path)
        return _normalize_index(df)
    df = pd.read_csv(path, index_col=0)
    return _normalize_index(df)


# Populated when load() is called with csv_path, so callers can print the
# validation report without re-reading the file.
_LAST_REPORT: dict = {}


def last_csv_report() -> dict:
    return dict(_LAST_REPORT)


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce the index to tz-naive timestamps (intraday files carry offsets)."""
    idx = pd.to_datetime(df.index, utc=True, errors="coerce")
    df.index = idx.tz_convert(None)
    df = df[~df.index.isna()].sort_index()
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--intraday", action="store_true", help="also fetch 5m bars")
    ap.add_argument("--csv", metavar="PATH",
                    help="load a Deriv/MT5 export instead of downloading; prints "
                         "a validation report and writes a normalised copy to "
                         "research/data/ (the raw file is left untouched)")
    ap.add_argument("--name", default="h1", help="series name for --csv output")
    ap.add_argument("--shift-hours", type=float, default=0.0,
                    help="shift --csv timestamps to align server time to UTC")
    args = ap.parse_args()

    if args.csv:
        import deriv_csv
        try:
            df, report = deriv_csv.load_csv(args.csv, shift_hours=args.shift_hours)
        except Exception as e:  # noqa: BLE001
            print(f"FAILED: {e}")
            return 1
        print(deriv_csv.format_report(report))
        os.makedirs(DATA_DIR, exist_ok=True)
        out = os.path.join(DATA_DIR, f"{SYMBOL.replace('=', '_')}_{args.name}.csv")
        df.to_csv(out)
        print(f"\nnormalised copy -> {out}")
        print(f"raw file left untouched: {os.path.abspath(args.csv)}")
        return 0

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
