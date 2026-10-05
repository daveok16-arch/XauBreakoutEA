#!/usr/bin/env python3
"""
Long-history H1/H4 study - the experiment that decides whether we may act.

Runs the five pre-registered steps on an imported Deriv/MT5 H1 series:

  1. H1 only        - long history
  2. H4 only        - long history
  3. H1 + H4        - independent 0.75% legs
  4. H1 + H4        - shared risk cap
  5. OOS / regime breakdown

H4 parameters are FIXED at the harness defaults. They are deliberately NOT
optimised against the imported history: the purpose of this run is to validate a
hypothesis already formed, not to search for one.

Usage:
    python3 research/long_history.py --csv path/to/XAUUSD_H1.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

import deriv_csv
import fetch_data
import h4 as h4mod
import portfolio
import strategy
from strategy import Params

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
DERIV = dict(spread=0.30, commission_per_side=0.0)


def regime_of(seg: pd.DataFrame) -> str:
    ret = (seg["Close"].iloc[-1] / seg["Close"].iloc[0] - 1) * 100
    if ret > 10:
        return f"bull ({ret:+.0f}%)"
    if ret < -10:
        return f"bear ({ret:+.0f}%)"
    return f"chop ({ret:+.0f}%)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Deriv/MT5 H1 export")
    ap.add_argument("--shift-hours", type=float, default=0.0)
    ap.add_argument("--folds", type=int, default=8)
    args = ap.parse_args()

    os.makedirs(REPORT_DIR, exist_ok=True)
    h1, rep = deriv_csv.load_csv(args.csv, shift_hours=args.shift_hours)
    print(deriv_csv.format_report(rep))

    p = Params(**DERIV)
    h4 = h4mod.resample_h4(h1)
    plan_h1 = h4mod.h1_entry_plan(h1, p)
    plan_h4 = h4mod.entry_plan(h1, h4, p)

    print(f"\nH1 {h1.index.min().date()}..{h1.index.max().date()}  {len(h1)} bars "
          f"({(h1.index.max()-h1.index.min()).days/365.25:.1f} years)")
    print(f"H4 {len(h4)} bars, {len(plan_h4)} signals")
    print(f"FIXED params (not tuned): lookback={p.lookback} atr={p.atr_period} "
          f"stop={p.stop_atr}ATR rr={p.reward_risk} trail={p.trail_atr}ATR "
          f"risk={p.risk_pct}% cap={p.max_total_risk_pct}%")

    variants = {
        "1_H1_only": ({"H1": plan_h1}, True),
        "2_H4_only": ({"H4": plan_h4}, True),
        "3_H1_H4_indep": ({"H1": plan_h1, "H4": plan_h4}, False),
        "4_H1_H4_shared": ({"H1": plan_h1, "H4": plan_h4}, True),
    }

    rows, all_trades = [], {}
    for name, (plans, shared) in variants.items():
        curve, trades, dd = portfolio._simulate(h1, p, plans, shared)
        m = strategy.metrics(curve, trades, dd, p)
        m["variant"] = name
        rows.append(m)
        all_trades[name] = trades
        print(f"\n=== {name} ===")
        print(f"  trades={m['trades']}  CAGR={m['cagr_pct']:.1f}%  net={m['total_return_pct']:.1f}%  "
              f"maxDD={m['max_dd_pct']:.1f}%  PF={m['profit_factor']:.2f}  "
              f"win/loss={m['avg_win_loss_ratio']:.2f}  win%={m['win_rate']:.1f}")

    ov = portfolio.overlap_stats(all_trades["4_H1_H4_shared"])
    print(f"\n=== overlap (shared) ===")
    print(f"  pairs={ov.get('overlapping_pairs',0)}  same dir={ov.get('same_direction',0)} "
          f"({ov.get('same_dir_share_pct',0):.1f}%)  opp dir={ov.get('opposite_direction',0)}")

    # ---- step 5: OOS / regime breakdown --------------------------------
    print(f"\n=== step 5: out-of-sample segments ({args.folds}) ===")
    n = len(h1)
    size = n // args.folds
    seg_rows = []
    for k in range(args.folds):
        lo, hi = k * size, (k + 1) * size
        seg = h1.iloc[lo:hi]
        row = dict(seg=k + 1, period=f"{seg.index[0].date()}..{seg.index[-1].date()}",
                   regime=regime_of(seg))
        for name, (plans, shared) in variants.items():
            sub = {leg: {i - lo: v for i, v in pl.items() if lo <= i < hi}
                   for leg, pl in plans.items()}
            c, t, dd = portfolio._simulate(seg, p, sub, shared)
            m = strategy.metrics(c, t, dd, p)
            row[f"{name}_ret"] = m.get("total_return_pct", 0)
            row[f"{name}_dd"] = m.get("max_dd_pct", 0)
        seg_rows.append(row)
    res = pd.DataFrame(seg_rows)
    names = list(variants.keys())
    print(f"  {'seg':>3s} {'period':24s} {'regime':16s} " +
          " ".join(f"{n[:9]:>10s}" for n in names))
    for _, r in res.iterrows():
        print(f"  {r.seg:3d} {r.period:24s} {r.regime:16s} " +
              " ".join(f"{r[n+'_ret']:10.1f}" for n in names))
    print()
    for n in names:
        rr = res[n + "_ret"]
        print(f"  {n:16s}: mean={rr.mean():6.1f}%  median={rr.median():6.1f}%  "
              f"positive={int((rr>0).sum())}/{len(rr)}  worstDD={res[n+'_dd'].max():.1f}%")

    out = pd.DataFrame([{k: v for k, v in r.items() if k != "exits"} for r in rows])
    out.to_csv(os.path.join(REPORT_DIR, "long_history_variants.csv"), index=False)
    res.to_csv(os.path.join(REPORT_DIR, "long_history_regimes.csv"), index=False)
    print(f"\nsaved CSVs to {REPORT_DIR}/")

    # ---- explicit verdict on the production gate -----------------------
    shared = next(r for r in rows if r["variant"] == "4_H1_H4_shared")
    h1only = next(r for r in rows if r["variant"] == "1_H1_only")
    sr = res["4_H1_H4_shared_ret"]
    years = (h1.index.max() - h1.index.min()).days / 365.25
    regimes = set(r.split(" ")[0] for r in res["regime"])
    print("\n=== production gate ===")
    print(f"  history length            : {years:.1f} years")
    print(f"  distinct regimes covered  : {sorted(regimes)}")
    print(f"  shared vs H1-only CAGR    : {shared['cagr_pct']:.1f}% vs {h1only['cagr_pct']:.1f}%")
    print(f"  shared vs H1-only maxDD   : {shared['max_dd_pct']:.1f}% vs {h1only['max_dd_pct']:.1f}%")
    print(f"  shared positive segments  : {int((sr>0).sum())}/{len(sr)}")
    # A short, single-regime window can pass the performance test by luck. Require
    # enough history and more than one regime before granting permission.
    enough_history = years >= 8.0
    enough_regimes = len(regimes) >= 2
    perf_ok = (shared["cagr_pct"] > h1only["cagr_pct"]
               and shared["max_dd_pct"] <= h1only["max_dd_pct"] + 1.0
               and (sr > 0).mean() >= 0.75)
    if not enough_history:
        print(f"  BLOCKED: {years:.1f} years < 8.0 required. A short window cannot grant permission.")
    if not enough_regimes:
        print(f"  BLOCKED: only one regime ({sorted(regimes)}) covered.")
    verdict = enough_history and enough_regimes and perf_ok
    print(f"  VERDICT: {'permission to wire into the EA (default-off)' if verdict else 'NOT sufficient - stay in research'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
