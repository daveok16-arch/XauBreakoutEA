#!/usr/bin/env python3
"""
Deriv / MT5 CSV loader for the strategy harness.

Deliberately boring and strict. It reads the common broker export shapes, builds
ONE explicit timezone convention, and refuses to hide data problems.

What it accepts
  - delimiter: comma, semicolon or tab (sniffed)
  - timestamp: a single datetime column, or separate Date + Time columns
  - columns: Open, High, Low, Close (+ optional Volume/TickVolume/RealVolume)
  - header names are matched case-insensitively and may carry a broker prefix
    (e.g. "XAUUSD_Open", "<OPEN>", "XAUUSD.Open")
  - the "<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>"
    shape MT5 writes is handled, including its often-empty trailing columns

Timezone convention
  MT5 exports the broker *server* time with no offset. This loader records the
  raw wall clock as a tz-naive UTC-normalised series and NEVER guesses an offset.
  The convention is explicit and carried through: timestamps are treated as UTC.
  If your broker is not UTC, pass --shift-hours to align, and note it, because
  it changes session boundaries.

Guarantees
  - rows are sorted ascending and exact duplicate timestamps are removed
  - OHLC consistency is validated (high >= max(open,close), low <= min(...),
    high >= low, positive prices)
  - gaps are FLAGGED, never filled
  - the raw file is never modified; the loader only reads it

Usage (library):
    from deriv_csv import load_csv
    df, report = load_csv("XAUUSD_H1.csv")

Usage (report only):
    python3 research/deriv_csv.py path/to/XAUUSD_H1.csv
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

OHLC = ["Open", "High", "Low", "Close"]

_TS_PATTERNS = [
    "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
]


@dataclass
class LoadReport:
    source: str
    rows_in_file: int = 0
    malformed_rows: int = 0
    duplicate_timestamps: int = 0
    ohlc_inconsistent: int = 0
    nonpositive_prices: int = 0
    rows_kept: int = 0
    start: str = ""
    end: str = ""
    inferred_tf: str = ""
    gaps: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    timestamp_column: str = ""
    timezone_convention: str = "naive-UTC (raw wall clock, no offset applied)"
    shift_hours: float = 0.0
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def _sniff_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in [",", ";", "\t"]}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _normalize_header(name: str) -> str:
    """Reduce a header cell to a bare field name: 'XAUUSD_OPEN' -> 'open'."""
    n = name.strip().strip("<>").strip().lower()
    n = re.split(r"[._\s]+", n)[-1] if re.search(r"[._\s]", n) else n
    return n


def _read_frame(path: str) -> tuple[pd.DataFrame, str, str]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = _strip_bom(fh.read())
    delim = _sniff_delimiter(text[:4096])
    df = pd.read_csv(io.StringIO(text), sep=delim, dtype=str, skipinitialspace=True,
                     keep_default_na=False, na_values=[""])
    df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]]
    return df, delim, text


def _find_columns(df: pd.DataFrame) -> dict:
    """Map canonical field -> actual column name."""
    norm = {_normalize_header(str(c)): c for c in df.columns}
    found: dict[str, str] = {}
    for f in OHLC:
        if f.lower() in norm:
            found[f] = norm[f.lower()]
    for alias, canon in (("volume", "Volume"), ("tickvol", "Volume"),
                         ("realvol", "Volume"), ("vol", "Volume")):
        if alias in norm and "Volume" not in found:
            found["Volume"] = norm[alias]
    # A bare "time" column is only a clock time, never a full timestamp; it must
    # be combined with the date column, or the date is silently lost.
    for alias in ("datetime", "date_time", "timestamp", "dt"):
        if alias in norm:
            found["timestamp"] = norm[alias]
            break
    for alias in ("date", "day"):
        if alias in norm:
            found["date"] = norm[alias]
            break
    if "time" in norm:
        found["time"] = norm["time"]
    return found


def _parse_timestamps(df: pd.DataFrame, cols: dict) -> tuple[pd.Series, list[str]]:
    warnings: list[str] = []
    if "timestamp" in cols:
        raw = df[cols["timestamp"]].astype(str).str.strip()
        ts = pd.to_datetime(raw, format=None, errors="coerce", dayfirst=False)
        if ts.isna().mean() > 0.5:
            for pat in _TS_PATTERNS:
                trial = pd.to_datetime(raw, format=pat, errors="coerce")
                if trial.notna().mean() > 0.9:
                    ts = trial
                    break
        return ts, warnings
    if "date" in cols:
        raw = df[cols["date"]].astype(str).str.strip()
        if "time" in cols:
            raw = raw + " " + df[cols["time"]].astype(str).str.strip()
        ts = pd.to_datetime(raw, errors="coerce", dayfirst=False)
        if ts.isna().mean() > 0.5:
            for pat in _TS_PATTERNS:
                trial = pd.to_datetime(raw, format=pat, errors="coerce")
                if trial.notna().mean() > 0.9:
                    ts = trial
                    break
        return ts, warnings
    raise ValueError("no timestamp column found (need a datetime, or date+time)")


def _infer_timeframe(idx: pd.DatetimeIndex) -> str:
    if len(idx) < 3:
        return "unknown"
    deltas = pd.Series(idx).diff().dropna().dt.total_seconds() / 60.0
    deltas = deltas[deltas > 0]
    if deltas.empty:
        return "unknown"
    base = float(deltas.mode().iloc[0])
    names = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1",
             240: "H4", 1440: "D1", 10080: "W1"}
    if base in names:
        return names[base]
    if base < 1:
        return f"{int(base*60)}s"
    return f"{base:g}min"


def _find_gaps(idx: pd.DatetimeIndex, base_minutes: float, max_report: int = 20):
    """Flag interior gaps larger than one bar. Never fills them."""
    gaps = []
    if len(idx) < 2 or base_minutes <= 0:
        return gaps
    deltas = pd.Series(idx).diff().dt.total_seconds() / 60.0
    for i in range(1, len(idx)):
        d = deltas.iloc[i]
        if d > base_minutes * 1.5:
            gaps.append({
                "after": str(idx[i - 1]),
                "before": str(idx[i]),
                "gap_minutes": round(float(d), 1),
                "missing_bars": int(round(d / base_minutes)) - 1,
            })
    if len(gaps) > max_report:
        return gaps[:max_report] + [{"note": f"... {len(gaps)-max_report} more gaps"}]
    return gaps


def load_csv(path: str, shift_hours: float = 0.0, keep_volume: bool = True):
    """Load a Deriv/MT5 CSV into the harness schema.

    Returns (DataFrame indexed by tz-naive datetime with OHLC[+Volume], LoadReport).
    Raises ValueError if the file cannot be interpreted; never mutates the file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    raw, delim, _ = _read_frame(path)
    rep = LoadReport(source=os.path.abspath(path), shift_hours=shift_hours)
    rep.rows_in_file = len(raw)
    rep.columns = [str(c) for c in raw.columns]

    cols = _find_columns(raw)
    missing = [f for f in OHLC if f not in cols]
    if missing:
        raise ValueError(f"missing OHLC columns {missing}; found {list(raw.columns)}")

    ts, warns = _parse_timestamps(raw, cols)
    rep.timestamp_column = cols.get("timestamp", cols.get("date", ""))
    rep.warnings.extend(warns)

    # --- numeric conversion; count rows we cannot use -------------------
    num = pd.DataFrame({f: pd.to_numeric(raw[cols[f]], errors="coerce") for f in OHLC})
    if keep_volume and "Volume" in cols:
        num["Volume"] = pd.to_numeric(raw[cols["Volume"]], errors="coerce").fillna(0.0)

    usable = ts.notna() & num[OHLC].notna().all(axis=1)
    rep.malformed_rows = int((~usable).sum())

    df = num.loc[usable].copy()
    df.index = pd.DatetimeIndex(ts.loc[usable])
    if shift_hours:
        df.index = df.index + pd.Timedelta(hours=shift_hours)

    # --- sort + deduplicate (exact duplicate timestamps) ----------------
    df = df.sort_index()
    dup = df.index.duplicated(keep="first")
    rep.duplicate_timestamps = int(dup.sum())
    df = df[~dup]

    # --- OHLC consistency ----------------------------------------------
    hi_ok = df["High"] >= df[["Open", "Close"]].max(axis=1)
    lo_ok = df["Low"] <= df[["Open", "Close"]].min(axis=1)
    range_ok = df["High"] >= df["Low"]
    pos_ok = (df[OHLC] > 0).all(axis=1)
    # categories are non-overlapping: a nonpositive row is reported once, and the
    # OHLC-consistency count only considers rows with positive prices.
    rep.nonpositive_prices = int((~pos_ok).sum())
    rep.ohlc_inconsistent = int((pos_ok & ~(hi_ok & lo_ok & range_ok)).sum())
    bad = ~(pos_ok & hi_ok & lo_ok & range_ok)
    if bad.any():
        rep.warnings.append(f"{int(bad.sum())} rows dropped for inconsistent/nonpositive OHLC")
        df = df[~bad]

    if df.empty:
        raise ValueError("no valid rows after cleaning")

    rep.rows_kept = len(df)
    rep.start, rep.end = str(df.index[0]), str(df.index[-1])
    rep.inferred_tf = _infer_timeframe(df.index)
    base_min = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240,
                "D1": 1440, "W1": 10080}.get(rep.inferred_tf, 0)
    if not base_min and rep.inferred_tf.endswith("min"):
        base_min = float(rep.inferred_tf[:-3])
    rep.gaps = _find_gaps(df.index, base_min)

    if rep.duplicate_timestamps:
        rep.warnings.append(f"{rep.duplicate_timestamps} duplicate timestamps removed (kept first)")
    if rep.gaps:
        rep.warnings.append(f"{len(rep.gaps)} interior gaps flagged (not filled)")

    df.index.name = "datetime"
    return df[OHLC + (["Volume"] if "Volume" in df.columns else [])], rep


def format_report(rep: LoadReport) -> str:
    lines = [
        f"=== CSV validation report ===",
        f"  source              : {rep.source}",
        f"  rows in file        : {rep.rows_in_file}",
        f"  malformed rows      : {rep.malformed_rows}",
        f"  duplicates removed  : {rep.duplicate_timestamps}",
        f"  OHLC inconsistent   : {rep.ohlc_inconsistent}",
        f"  nonpositive prices  : {rep.nonpositive_prices}",
        f"  rows kept           : {rep.rows_kept}",
        f"  date range          : {rep.start} .. {rep.end}",
        f"  inferred timeframe  : {rep.inferred_tf}",
        f"  timestamp column    : {rep.timestamp_column}",
        f"  timezone convention : {rep.timezone_convention}"
        + (f" (shifted {rep.shift_hours:+g}h)" if rep.shift_hours else ""),
        f"  gaps flagged        : {len(rep.gaps)}",
    ]
    for g in rep.gaps[:10]:
        if "note" in g:
            lines.append(f"      {g['note']}")
        else:
            lines.append(f"      {g['after']} -> {g['before']}  "
                         f"({g['gap_minutes']:g} min, {g['missing_bars']} bars)")
    for w in rep.warnings:
        lines.append(f"  warning             : {w}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a Deriv/MT5 CSV export.")
    ap.add_argument("path")
    ap.add_argument("--shift-hours", type=float, default=0.0,
                    help="shift timestamps to align broker server time to UTC")
    args = ap.parse_args()
    try:
        _, rep = load_csv(args.path, shift_hours=args.shift_hours)
    except Exception as e:  # noqa: BLE001 - report, don't traceback
        print(f"FAILED: {e}")
        return 1
    print(format_report(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
