#!/usr/bin/env python3
"""
Robustness checks that decide whether a backtest edge is real or fragile.

  1. Parameter sensitivity - nudge each input +/-. A strategy that only works
     at one exact setting is curve-fit; a robust one degrades gracefully.
  2. Cost stress - rerun with doubled spread and commission. Scalping/breakout
     edges are usually the first to die when costs rise.
  3. Trade-order Monte Carlo - shuffle the realised trade sequence to get a
     distribution of drawdowns, since the historical order is just one draw.

Usage:
    python3 research/robustness.py --tf daily
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

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# a stable, mid-range config chosen from the walk-forward folds
BASE_CFG = dict(lookback=60, stop_atr=1.5, reward_risk=2.0, trail_atr=2.0)


def run(df, p):
    curve, trades, dd = strategy.backtest(df, p)
    return strategy.metrics(curve, trades, dd, p), trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1"])
    ap.add_argument("--mc", type=int, default=2000)
    args = ap.parse_args()

    df = fetch_data.load(args.tf)
    base = replace(strategy.Params(), **BASE_CFG)
    m0, trades0 = run(df, base)
    print(f"baseline [{args.tf}]: ret={m0['total_return_pct']:.1f}%  dd={m0['max_dd_pct']:.1f}%  "
          f"pf={m0['profit_factor']:.2f}  n={m0['trades']}\n")

    # ---- 1) parameter sensitivity --------------------------------------
    print("=== parameter sensitivity (one-at-a-time) ===")
    perturb = {
        "lookback": [40, 50, 60, 70, 80],
        "stop_atr": [1.0, 1.25, 1.5, 1.75, 2.0],
        "reward_risk": [1.5, 1.75, 2.0, 2.5, 3.0],
        "trail_atr": [1.5, 1.75, 2.0, 2.5, 3.0],
    }
    sens_rows = []
    for key, vals in perturb.items():
        line = []
        for v in vals:
            cfg = dict(BASE_CFG); cfg[key] = v
            m, _ = run(df, replace(base, **cfg))
            line.append(f"{v}:{m['total_return_pct']:5.1f}%/{m['profit_factor']:.2f}")
        sens_rows.append((key, "  ".join(line)))
        print(f"  {key:12s} {sens_rows[-1][1]}")

    # ---- 2) cost stress -------------------------------------------------
    print("\n=== cost stress (return% / PF) ===")
    for mult in [1.0, 2.0, 3.0]:
        p = replace(base, spread=base.spread * mult,
                    commission_per_side=base.commission_per_side * mult)
        m, _ = run(df, p)
        print(f"  costs x{mult:.0f}  spread={p.spread:.2f} comm={p.commission_per_side:.2f}  "
              f"ret={m['total_return_pct']:6.1f}%  pf={m['profit_factor']:.2f}")

    # ---- 3) bootstrap Monte Carlo --------------------------------------
    # Permuting trades cannot change the final sum, so we resample *with
    # replacement* to get a real distribution of outcomes.
    print("\n=== Monte Carlo (bootstrap resample of trades) ===")
    r = np.array([t.r_multiple for t in trades0])
    risk_money = base.start_equity * base.risk_pct / 100.0
    pnl = r * risk_money
    dds = []
    finals = []
    rng = np.random.default_rng(42)
    for _ in range(args.mc):
        order = rng.choice(pnl, size=len(pnl), replace=True)
        e = base.start_equity
        peak = e
        worst = 0.0
        for x in order:
            e += x
            peak = max(peak, e)
            worst = max(worst, (peak - e) / peak)
        dds.append(worst * 100)
        finals.append(e)
    dds = np.array(dds); finals = np.array(finals)
    print(f"  drawdown  p50={np.percentile(dds,50):.1f}%  p90={np.percentile(dds,90):.1f}%  p99={np.percentile(dds,99):.1f}%")
    print(f"  final eq  p05=${np.percentile(finals,5):,.0f}  p50=${np.percentile(finals,50):,.0f}  p95=${np.percentile(finals,95):,.0f}")
    print(f"  prob(ending below start): {(finals < base.start_equity).mean()*100:.1f}%")

    os.makedirs(REPORT_DIR, exist_ok=True)
    pd.DataFrame({"mc_drawdown_pct": dds, "mc_final_equity": finals}).to_csv(
        os.path.join(REPORT_DIR, f"montecarlo_{args.tf}.csv"), index=False
    )
    print(f"\nsaved to {REPORT_DIR}/montecarlo_{args.tf}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
