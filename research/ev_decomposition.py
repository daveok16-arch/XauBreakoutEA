#!/usr/bin/env python3
"""
EV decomposition: where does the breakout edge's expectancy actually come from?

This does NOT add strategies. It takes the one mechanism we already have
(Donchian breakout, ATR risk, 2R target, trailing stop) and splits its trades
into buckets, then asks of each bucket: is this angle PROVEN?

An angle is only called proven when all three hold:
  1. enough trades to mean something (n >= MIN_N)
  2. positive expectancy that is statistically distinguishable from zero
     (one-sided t-stat on per-trade R)
  3. the same sign in every chronological chunk of the sample (not one lucky era)

Anything else is reported as NOT PROVEN or INCONCLUSIVE - never quietly folded
into a headline number.

Usage:
    python3 research/ev_decomposition.py --tf daily
    python3 research/ev_decomposition.py --tf h1
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

import fetch_data
import strategy
from strategy import Params

MIN_N = 30          # minimum trades for an angle to be judged at all
T_THRESHOLD = 1.65  # ~one-sided 95%


def _t_stat(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def _chunk_consistency(r: np.ndarray, times: list, chunks: int = 4) -> tuple[int, int]:
    """How many chronological chunks have positive mean R."""
    order = np.argsort([pd.Timestamp(t) for t in times])
    r = r[order]
    if len(r) < chunks * 5:
        return (0, 0)
    pos = 0
    for part in np.array_split(r, chunks):
        if len(part) and part.mean() > 0:
            pos += 1
    return pos, chunks


def verdict(r: np.ndarray, times: list) -> str:
    n = len(r)
    if n < MIN_N:
        return "NOT PROVEN (too few trades)"
    t = _t_stat(r)
    pos, tot = _chunk_consistency(r, times)
    if t >= T_THRESHOLD and pos == tot and tot > 0:
        return "PROVEN"
    if t >= T_THRESHOLD and pos < tot:
        return f"INCONCLUSIVE (edge not stable: {pos}/{tot} chunks positive)"
    if t <= -T_THRESHOLD:
        return "NEGATIVE (reliably loses)"
    return "NOT PROVEN (indistinguishable from zero)"


def _row(name: str, r: np.ndarray, times: list) -> dict:
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    wins = r[r > 0]
    losses = r[r < 0]
    gp = wins.sum()
    gl = -losses.sum()
    return {
        "bucket": name,
        "n": len(r),
        "win_pct": (len(wins) / len(r) * 100) if len(r) else 0.0,
        "avg_r": r.mean() if len(r) else 0.0,
        "pf": (gp / gl) if gl > 0 else float("inf"),
        "t_stat": _t_stat(r),
        "verdict": verdict(r, times) if len(r) else "NOT PROVEN (empty)",
    }


def _print(rows: list[dict], title: str):
    print(f"\n=== {title} ===")
    print(f"  {'bucket':32s} {'n':>5s} {'win%':>6s} {'avgR':>7s} {'PF':>6s} {'t':>6s}  verdict")
    for x in rows:
        print(f"  {x['bucket']:32s} {x['n']:5d} {x['win_pct']:6.1f} {x['avg_r']:7.3f} "
              f"{x['pf']:6.2f} {x['t_stat']:6.2f}  {x['verdict']}")


def decompose(trades: list, label: str):
    r = np.array([t.r_multiple for t in trades], dtype=float)
    times = [t.entry_time for t in trades]
    sides = np.array([t.side for t in trades])
    reasons = np.array([t.reason for t in trades])
    years = np.array([pd.Timestamp(t.entry_time).year for t in trades])
    bars = np.array([t.bars_held for t in trades], dtype=float)

    rows = [_row("ALL", r, times)]

    # by side
    for s in ("long", "short"):
        m = sides == s
        rows.append(_row(f"side={s}", r[m], [t for t, k in zip(times, m) if k]))

    # by exit reason - DESCRIPTIVE ONLY: these are deterministic by rule
    # (a target exit is always ~+RR, a stop always ~-1R), so a t-test on them is
    # a tautology. Reported for shape, never as evidence.
    for rs in sorted(set(reasons)):
        m = reasons == rs
        row = _row(f"exit={rs}", r[m], [t for t, k in zip(times, m) if k])
        row["verdict"] = "(descriptive - deterministic by rule)"
        rows.append(row)

    # by holding time: does the edge come from quick targets or long runners?
    q = np.quantile(bars, [0.25, 0.5, 0.75]) if len(bars) >= 8 else None
    if q is not None:
        labels = np.digitize(bars, q)
        for i, nm in enumerate(["shortest-25%", "25-50%", "50-75%", "longest-25%"]):
            m = labels == i
            rows.append(_row(f"hold={nm}", r[m], [t for t, k in zip(times, m) if k]))

    _print(rows, f"EV decomposition [{label}]")
    return rows


def by_year(trades: list, label: str):
    r = np.array([t.r_multiple for t in trades], dtype=float)
    years = np.array([pd.Timestamp(t.entry_time).year for t in trades])
    print(f"\n=== per-year expectancy [{label}] ===")
    print(f"  {'year':6s} {'n':>4s} {'win%':>6s} {'avgR':>7s} {'sumR':>8s}")
    for y in sorted(set(years)):
        m = years == y
        rr = r[m]
        w = (rr > 0).mean() * 100 if len(rr) else 0
        print(f"  {y:6d} {len(rr):4d} {w:6.1f} {rr.mean():7.3f} {rr.sum():8.2f}")


def sensitivity(df, base: Params, label: str):
    """One-parameter-at-a-time: what actually moves expectancy?"""
    print(f"\n=== parameter sensitivity (avg R) [{label}] ===")
    grid = {
        "lookback": [20, 40, 60, 120, 250],
        "stop_atr": [1.0, 1.5, 2.0, 3.0],
        "reward_risk": [1.0, 1.5, 2.0, 3.0, 4.0],
        "trail_atr": [1.0, 2.0, 3.0],
        "atr_period": [7, 14, 21],
    }
    for k, vals in grid.items():
        line = []
        for v in vals:
            p = replace(base, **{k: v})
            _, trades, _ = strategy.backtest(df, p)
            rr = np.array([t.r_multiple for t in trades]) if trades else np.array([])
            line.append(f"{v}:{rr.mean():+.3f}({len(rr)})")
        print(f"  {k:14s} " + "  ".join(line))


def benchmark(df, base: Params, label: str):
    """The bar the strategy must clear: simply holding gold."""
    bh = df["Close"]
    years = (bh.index[-1] - bh.index[0]).days / 365.25
    bh_cagr = ((bh.iloc[-1] / bh.iloc[0]) ** (1 / years) - 1) * 100
    run = bh.cummax()
    bh_dd = ((run - bh) / run).max() * 100

    def run_variant(name, p):
        cur, tr, dd = strategy.backtest(df, p)
        m = strategy.metrics(cur, tr, dd, p)
        return (f"  {name:22s} CAGR {m['cagr_pct']:5.1f}%  maxDD {m['max_dd_pct']:5.1f}%  "
                f"PF {m['profit_factor']:4.2f}  avgR {m['avg_r']:+.3f}  n {m['trades']}")

    print(f"\n=== vs buy-and-hold [{label}] {bh.index[0].date()}..{bh.index[-1].date()} ({years:.1f}y) ===")
    print(f"  {'buy & hold gold':22s} CAGR {bh_cagr:5.1f}%  maxDD {bh_dd:5.1f}%")
    print(run_variant("breakout long+short", base))
    print(run_variant("breakout long-only", replace(base, allow_short=False)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1", "m5"])
    args = ap.parse_args()

    df = fetch_data.load(args.tf)
    p = Params()
    curve, trades, max_dd = strategy.backtest(df, p)
    m = strategy.metrics(curve, trades, max_dd, p)
    print(f"base config [{args.tf}] {df.index.min().date()}..{df.index.max().date()}: "
          f"{m['trades']} trades, PF {m['profit_factor']:.2f}, avgR {m['avg_r']:.3f}")

    decompose(trades, args.tf)
    by_year(trades, args.tf)
    benchmark(df, p, args.tf)
    sensitivity(df, p, args.tf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
