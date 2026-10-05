#!/usr/bin/env python3
"""
Import validation gate.

Two checks, in order of what they can prove.

1. Self-consistency gate (runnable now, no new data needed)
   Take the known-good cached H1 series, serialise it to a broker-style CSV,
   push it back through the Deriv/MT5 loader, and require an identical result:
   same timestamps -> same OHLC -> same signal -> same entry -> same trade
   sequence. This validates the whole normalisation pipeline end to end. If it
   fails, the loader is broken and nothing downstream can be trusted.

2. Overlap gate (when the long CSV is supplied)
   Compare the imported series against the existing series over their overlap.
   If they are the same instrument, require an exact OHLC and trade-sequence
   match and STOP on any divergence - that would be a normalisation or
   session-boundary bug, not a discovery.
   If they are different instruments (the existing cache is a COMEX futures
   proxy, a Deriv export is spot), an exact match is impossible by construction;
   the gate then reports the divergence, scans for a timezone/session shift, and
   refuses to claim a pass.

Usage:
    python3 research/validate_import.py                          # self-check
    python3 research/validate_import.py --csv path/XAUUSD_H1.csv # + overlap
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import replace

import numpy as np
import pandas as pd

import deriv_csv
import fetch_data
import strategy
from strategy import Params

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
OHLC = ["Open", "High", "Low", "Close"]


def trade_signature(df: pd.DataFrame, p: Params):
    """A comparable fingerprint of the full trade sequence."""
    _, trades, _ = strategy.backtest(df, p)
    return [
        (str(t.entry_time), str(t.exit_time), t.side, round(t.entry, 6),
         round(t.exit, 6), round(t.size, 8), round(t.pnl, 6), t.reason)
        for t in trades
    ]


def to_broker_csv(df: pd.DataFrame, path: str):
    """Serialise a harness frame into a broker-style Date,Time,OHLC,Volume CSV."""
    out = pd.DataFrame({
        "Date": df.index.strftime("%Y.%m.%d"),
        "Time": df.index.strftime("%H:%M:%S"),
        "Open": df["Open"].to_numpy(),
        "High": df["High"].to_numpy(),
        "Low": df["Low"].to_numpy(),
        "Close": df["Close"].to_numpy(),
    })
    if "Volume" in df.columns:
        out["Volume"] = df["Volume"].to_numpy()
    out.to_csv(path, index=False)


def gate_self_consistency(tf: str = "h1") -> bool:
    print("=== gate 1: loader self-consistency ===")
    cached = fetch_data.load(tf)
    p = Params(spread=0.30, commission_per_side=0.0)
    sig_cached = trade_signature(cached, p)

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "roundtrip.csv")
        to_broker_csv(cached, csv_path)
        loaded, rep = deriv_csv.load_csv(csv_path)
        # second pass through the loader (idempotency on the normalised copy)
        norm_path = os.path.join(tmp, "normalised.csv")
        loaded.to_csv(norm_path)
        reloaded, _ = deriv_csv.load_csv(norm_path)

    ok = True

    same_index = cached.index.equals(loaded.index)
    print(f"  timestamps identical      : {same_index}  ({len(cached)} vs {len(loaded)})")
    ok &= same_index

    same_ohlc = bool(np.allclose(cached[OHLC].to_numpy(), loaded[OHLC].to_numpy(), atol=1e-9))
    print(f"  OHLC identical            : {same_ohlc}")
    ok &= same_ohlc

    idem = bool(np.allclose(loaded[OHLC].to_numpy(), reloaded[OHLC].to_numpy(), atol=1e-9)) \
        and loaded.index.equals(reloaded.index)
    print(f"  loader idempotent         : {idem}")
    ok &= idem

    sig_loaded = trade_signature(loaded, p)
    same_trades = sig_cached == sig_loaded
    print(f"  trade sequence identical  : {same_trades}  ({len(sig_cached)} trades)")
    ok &= same_trades

    if not same_trades:
        for a, b in zip(sig_cached, sig_loaded):
            if a != b:
                print(f"    first divergence: cached={a}")
                print(f"                      loaded={b}")
                break

    print(f"  malformed={rep.malformed_rows} dup={rep.duplicate_timestamps} "
          f"gaps={len(rep.gaps)} tf={rep.inferred_tf}")
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def _hour_hist(idx: pd.DatetimeIndex) -> pd.Series:
    return idx.hour.value_counts().sort_index()


def gate_overlap(csv_path: str, tf: str = "h1") -> bool:
    print("\n=== gate 2: imported vs existing, overlapping period ===")
    existing = fetch_data.load(tf)
    imported, rep = deriv_csv.load_csv(csv_path)
    print(deriv_csv.format_report(rep))

    lo = max(existing.index.min(), imported.index.min())
    hi = min(existing.index.max(), imported.index.max())
    print(f"\n  overlap window            : {lo} .. {hi}")
    if lo >= hi:
        print("  no overlap between imported and existing series - cannot gate.")
        return False

    e = existing.loc[(existing.index >= lo) & (existing.index <= hi)]
    i = imported.loc[(imported.index >= lo) & (imported.index <= hi)]
    common = e.index.intersection(i.index)
    print(f"  existing bars in overlap  : {len(e)}")
    print(f"  imported bars in overlap  : {len(i)}")
    print(f"  common timestamps         : {len(common)}")

    if len(common) == 0:
        print("  no common timestamps - session-boundary mismatch. STOP.")
        return False

    ec = e.loc[common, OHLC].to_numpy()
    ic = i.loc[common, OHLC].to_numpy()
    close_eq = np.isclose(ec[:, 3], ic[:, 3], atol=1e-6)
    match_rate = close_eq.mean() * 100
    print(f"  close prices identical    : {match_rate:.2f}% of common timestamps")

    # session shape: do the two series trade the same hours?
    he, hi_ = _hour_hist(e.index), _hour_hist(i.index)
    print(f"  existing trading hours    : {sorted(he.index.tolist())}")
    print(f"  imported trading hours    : {sorted(hi_.index.tolist())}")

    same_source = match_rate > 99.9
    if same_source:
        print("\n  same instrument detected -> strict gate applies")
        p = Params(spread=0.30, commission_per_side=0.0)
        se, si = trade_signature(e, p), trade_signature(i, p)
        if se == si:
            print(f"  trade sequence identical  : True ({len(se)} trades)")
            print("  RESULT: PASS")
            return True
        print(f"  trade sequence identical  : False (existing {len(se)} vs imported {len(si)})")
        print("  RESULT: FAIL - STOP. This is a normalisation/session issue, not a discovery.")
        return False

    # Different instruments: an exact match is impossible. Look for a shift that
    # would indicate a timezone/session bug rather than a different instrument.
    print("\n  different instrument detected (existing cache is a COMEX futures proxy,")
    print("  the export is broker spot). An exact OHLC match is impossible by construction.")
    best = None
    for shift in range(-6, 7):
        shifted = imported.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=shift)
        cm = e.index.intersection(shifted.index)
        if len(cm) < 10:
            continue
        a = e.loc[cm, "Close"].to_numpy()
        b = shifted.loc[cm, "Close"].to_numpy()
        # level agreement is meaningless across instruments; use return correlation
        ra = np.diff(a) / a[:-1]
        rb = np.diff(b) / b[:-1]
        corr = np.corrcoef(ra, rb)[0, 1] if len(ra) > 2 else float("nan")
        if best is None or (corr == corr and corr > best[1]):
            best = (shift, corr)
    if best:
        print(f"  best hour shift           : {best[0]:+d}h  (return corr {best[1]:.4f})")
        if best[0] != 0 and best[1] > 0.9:
            print("  WARNING: a nonzero shift fits much better - possible timezone/session bug. STOP.")
            return False

    print("\n  RESULT: INCONCLUSIVE - different instruments. The overlap gate cannot")
    print("  certify this import. Use the imported series for the long-history study")
    print("  only after confirming it is internally clean, and expect its 2024-2026")
    print("  numbers to differ from the futures-proxy baseline by construction.")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Deriv/MT5 export to validate against the cache")
    ap.add_argument("--tf", default="h1")
    args = ap.parse_args()

    ok = gate_self_consistency(args.tf)
    if args.csv:
        gate_overlap(args.csv, args.tf)
    else:
        print("\n(no --csv supplied; overlap gate skipped)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
