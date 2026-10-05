#!/usr/bin/env python3
"""
Preflight for a Deriv/MT5 H1 export.

Cheap, read-only checks to run BEFORE the expensive long-history experiment. It
answers one question: is this file worth spending the experiment on?

  - date range (and the earliest timestamp, which is the authority)
  - row count
  - inferred timeframe must be H1
  - duplicate count must be 0
  - gap count, reported and bucketed
  - history length vs a required minimum
  - bar density vs expectation (catches a long range that is sparsely populated)

Note on historical completeness: setting MT5's "Max bars in chart" to Unlimited
is necessary but not sufficient. If the broker's server history does not extend
far enough, the export can be perfectly valid and still too short. The earliest
timestamp in the file is the authority; this script compares it to the minimum
history the research gate requires.

Exit code 0 = clear to run the experiment, 1 = do not run it.

Usage:
    python3 research/preflight.py --csv ~/XAUUSD_H1.csv
    python3 research/preflight.py --csv ~/XAUUSD_H1.csv --min-years 8
"""
from __future__ import annotations

import argparse
import os
import sys

import deriv_csv

# Gold trades roughly 23h/day, 5 days/week -> ~115-120 H1 bars per week.
EXPECTED_BARS_PER_WEEK = 115.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--min-years", type=float, default=8.0,
                    help="minimum history the research gate requires (default 8)")
    ap.add_argument("--shift-hours", type=float, default=0.0)
    ap.add_argument("--expect-tf", default="H1")
    args = ap.parse_args()

    try:
        df, rep = deriv_csv.load_csv(args.csv, shift_hours=args.shift_hours)
    except Exception as e:  # noqa: BLE001
        print(f"PREFLIGHT: FAIL - cannot load file: {e}")
        return 1

    start, end = df.index[0], df.index[-1]
    days = (end - start).days
    years = days / 365.25
    weeks = days / 7.0
    expected_bars = weeks * EXPECTED_BARS_PER_WEEK
    density = len(df) / expected_bars * 100 if expected_bars else 0.0

    checks = []          # (name, ok, detail)
    checks.append(("date range", True, f"{start} .. {end}"))
    checks.append(("row count", len(df) > 0, f"{len(df)} bars"))
    checks.append((f"inferred timeframe = {args.expect_tf}", rep.inferred_tf == args.expect_tf,
                   f"{rep.inferred_tf}"))
    checks.append(("duplicate count = 0", rep.duplicate_timestamps == 0,
                   f"{rep.duplicate_timestamps} duplicates"))
    checks.append(("no malformed rows", rep.malformed_rows == 0,
                   f"{rep.malformed_rows} malformed"))
    checks.append(("no inconsistent OHLC", rep.ohlc_inconsistent == 0,
                   f"{rep.ohlc_inconsistent} inconsistent"))
    checks.append((f"history >= {args.min_years:g} years", years >= args.min_years,
                   f"{years:.1f} years"))
    checks.append(("bar density plausible (>=80% of expected)",
                   density >= 80.0, f"{density:.0f}% of ~{expected_bars:,.0f} expected"))

    print("=== preflight ===")
    for name, ok, detail in checks:
        print(f"  [{'ok' if ok else '!!'}] {name:42s} : {detail}")

    print(f"\n  earliest timestamp (authority) : {start}")
    print(f"  gaps flagged                   : {rep.gap_count}", end="")
    if rep.gap_buckets:
        print("  (" + "  ".join(f"{k}: {v}" for k, v in rep.gap_buckets.items()) + ")")
    else:
        print()

    hard_fail = [n for n, ok, _ in checks if not ok
                 and n not in ("no malformed rows", "no inconsistent OHLC")]
    soft_fail = [n for n, ok, _ in checks if not ok
                 and n in ("no malformed rows", "no inconsistent OHLC")]

    print()
    if soft_fail:
        print(f"  note: {', '.join(soft_fail)} - rows were dropped by the loader;")
        print("        check the dropped count is small before trusting the series.")
    if hard_fail:
        print(f"  PREFLIGHT: BLOCKED - {', '.join(hard_fail)}")
        if years < args.min_years:
            print(f"    history is {years:.1f} years, {args.min_years - years:.1f} short of the "
                  f"{args.min_years:g}-year gate.")
            print("    Check the broker's server history, not just 'Max bars in chart'.")
        print("    Do NOT run the long-history experiment on this file.")
        return 1

    print("  PREFLIGHT: CLEAR - safe to run the long-history experiment:")
    print(f"    python3 research/validate_import.py --csv {args.csv}")
    print(f"    python3 research/compare_instruments.py --csv {args.csv}")
    print(f"    python3 research/long_history.py --csv {args.csv} --folds 8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
