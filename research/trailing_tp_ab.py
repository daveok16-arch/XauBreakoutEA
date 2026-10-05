#!/usr/bin/env python3
"""
Controlled A/B test: fixed take-profit vs trailing take-profit.

Both modes are run on the *same* data, with the *same* cost, spread, commission
and risk settings. The only difference is the exit rule. That is the whole point:
if the trailing TP helps, it must be the exit rule doing it, not a different
cost model or risk budget.

Data note: the harness uses COMEX gold futures (GC=F) as the XAUUSD proxy - the
best free history available. Both modes see the identical series, so the
comparison is internally valid even though the proxy is not spot XAUUSD.

Usage:
    python3 research/trailing_tp_ab.py
    python3 research/trailing_tp_ab.py --tf h1
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

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# Shared assumptions - identical for BOTH modes.
# Deriv gold: zero commission, ~0.30 spread. Slippage is not modelled separately;
# the half-spread on entry and exit is the only execution cost in the harness.
DERIV = dict(spread=0.30, commission_per_side=0.0)

COLS = [
    ("cagr_pct", "CAGR %", "{:8.1f}"),
    ("total_return_pct", "net return %", "{:8.1f}"),
    ("max_dd_pct", "max DD %", "{:8.1f}"),
    ("profit_factor", "profit factor", "{:8.2f}"),
    ("avg_win_loss_ratio", "avg win/loss", "{:8.2f}"),
    ("win_rate", "win rate %", "{:8.1f}"),
    ("trades", "trades", "{:8d}"),
    ("avg_bars_held", "avg bars held", "{:8.1f}"),
    ("avg_r", "avg R", "{:8.2f}"),
    ("sharpe", "sharpe", "{:8.2f}"),
]


def run(df, p):
    curve, trades, dd = strategy.backtest(df, p)
    return strategy.metrics(curve, trades, dd, p)


def line(label, m, fmt):
    v = m.get(label.split("_pct")[0] if False else None, None)
    return v


def show(name, m):
    if not m.get("trades"):
        print(f"  {name:26s}: no trades")
        return
    print(f"  {name:26s}: " + "  ".join(f"{lbl}={fmt.format(m[k])}" for k, lbl, fmt in COLS))
    print(f"  {'':26s}  exits={m.get('exits')}")


def ab(df, label):
    base = Params(**DERIV)
    ttp = replace(base, use_trailing_tp=True, trail_tp_start_r=1.0, trail_tp_atr=1.0)
    m_base = run(df, base)
    m_ttp = run(df, ttp)
    print(f"\n=== {label}  {df.index.min().date()}..{df.index.max().date()}  ({len(df)} bars) ===")
    show("fixed TP (baseline)", m_base)
    show("trailing TP", m_ttp)
    return base, m_base, m_ttp


def sensitivity(df):
    """Vary the two trailing-TP knobs. Reported as a surface, not cherry-picked."""
    print("\n=== trailing-TP parameter surface (daily) ===")
    print(f"  {'start_r':>8s} {'trail_atr':>10s} {'CAGR%':>8s} {'maxDD%':>8s} {'PF':>6s} {'win/loss':>9s}")
    rows = []
    for sr in (0.5, 1.0, 1.5, 2.0):
        for ta in (0.5, 1.0, 1.5, 2.0):
            p = replace(Params(**DERIV), use_trailing_tp=True, trail_tp_start_r=sr, trail_tp_atr=ta)
            m = run(df, p)
            print(f"  {sr:8.1f} {ta:10.1f} {m['cagr_pct']:8.1f} {m['max_dd_pct']:8.1f} "
                  f"{m['profit_factor']:6.2f} {m['avg_win_loss_ratio']:9.2f}")
            rows.append(dict(start_r=sr, trail_atr=ta, **{k: m[k] for k, _, _ in COLS}))
    return pd.DataFrame(rows)


def oos_segments(df, folds=6):
    """Fixed-parameter out-of-sample check.

    Params are fixed a priori, so every segment is genuinely unseen. This
    isolates the exit change: both modes use identical parameters.
    """
    print(f"\n=== fixed-parameter out-of-sample segments ({folds}) ===")
    base = Params(**DERIV)
    ttp = replace(base, use_trailing_tp=True, trail_tp_start_r=1.0, trail_tp_atr=1.0)
    n = len(df)
    size = n // folds
    rows = []
    for k in range(folds):
        seg = df.iloc[k * size: (k + 1) * size]
        mb, mt = run(seg, base), run(seg, ttp)
        rows.append(dict(
            seg=k + 1,
            period=f"{seg.index[0].date()}..{seg.index[-1].date()}",
            base_ret=mb.get("total_return_pct", 0), ttp_ret=mt.get("total_return_pct", 0),
            base_dd=mb.get("max_dd_pct", 0), ttp_dd=mt.get("max_dd_pct", 0),
            base_pf=mb.get("profit_factor", 0), ttp_pf=mt.get("profit_factor", 0),
        ))
    res = pd.DataFrame(rows)
    print(f"  {'seg':>3s} {'period':24s} {'base ret':>9s} {'ttp ret':>9s} "
          f"{'base DD':>8s} {'ttp DD':>8s} {'base PF':>8s} {'ttp PF':>7s}")
    for _, r in res.iterrows():
        print(f"  {r.seg:3d} {r.period:24s} {r.base_ret:9.1f} {r.ttp_ret:9.1f} "
              f"{r.base_dd:8.1f} {r.ttp_dd:8.1f} {r.base_pf:8.2f} {r.ttp_pf:7.2f}")
    print(f"\n  base: mean ret={res.base_ret.mean():.1f}%  positive={int((res.base_ret>0).sum())}/{len(res)}")
    print(f"  ttp : mean ret={res.ttp_ret.mean():.1f}%  positive={int((res.ttp_ret>0).sum())}/{len(res)}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="both", choices=["daily", "h1", "both"])
    args = ap.parse_args()

    os.makedirs(REPORT_DIR, exist_ok=True)
    tfs = ["daily", "h1"] if args.tf == "both" else [args.tf]

    summary = []
    for tf in tfs:
        df = fetch_data.load(tf)
        base, mb, mt = ab(df, tf)
        summary.append(dict(tf=tf, mode="fixed_tp", **{k: mb.get(k) for k, _, _ in COLS}))
        summary.append(dict(tf=tf, mode="trailing_tp", **{k: mt.get(k) for k, _, _ in COLS}))

    daily = fetch_data.load("daily")
    sens = sensitivity(daily)
    segs = oos_segments(daily)

    pd.DataFrame(summary).to_csv(os.path.join(REPORT_DIR, "trailing_tp_ab.csv"), index=False)
    sens.to_csv(os.path.join(REPORT_DIR, "trailing_tp_sensitivity.csv"), index=False)
    segs.to_csv(os.path.join(REPORT_DIR, "trailing_tp_oos.csv"), index=False)
    print(f"\nsaved CSVs to {REPORT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
