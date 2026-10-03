#!/usr/bin/env python3
"""
Walk-forward validation.

A single backtest is meaningless: optimize on history and you will always find
a curve that fits. This splits the series into consecutive folds, optimizes on
each in-sample (IS) window, then measures the chosen parameters on the *next*,
unseen out-of-sample (OOS) window. Only the OOS results are evidence.

Usage:
    python3 research/walkforward.py --tf daily
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

import fetch_data
import strategy

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# deliberately small grid: a big grid manufactures overfitting
GRID = {
    "lookback": [20, 40, 60],
    "stop_atr": [1.0, 1.5, 2.0],
    "reward_risk": [1.5, 2.0, 3.0],
    "trail_atr": [1.5, 2.0, 3.0],
}


def combos(grid: dict):
    keys = list(grid)
    for vals in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def run_oos(df: pd.DataFrame, p: strategy.Params):
    curve, trades, dd = strategy.backtest(df, p)
    return strategy.metrics(curve, trades, dd, p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1"])
    ap.add_argument("--folds", type=int, default=6)
    args = ap.parse_args()

    df = fetch_data.load(args.tf)
    n = len(df)
    fold_size = n // (args.folds + 1)          # +1 so we always have an OOS tail
    if fold_size < 150:
        print("series too short for this fold count")
        return 1

    base = strategy.Params()
    rows = []
    print(f"walk-forward [{args.tf}] {args.folds} folds, IS={fold_size} bars\n")

    for k in range(args.folds):
        is_start = k * fold_size
        is_end = is_start + fold_size
        oos_end = min(is_end + fold_size, n)
        is_df = df.iloc[is_start:is_end]
        oos_df = df.iloc[is_end - base.lookback - base.atr_period: oos_end]  # warmup overlap

        best, best_score = None, -1e18
        for c in combos(GRID):
            p = replace(base, **c)
            m = run_oos(is_df, p)
            if m.get("trades", 0) < 10:
                continue
            # score = return per unit of drawdown, require a sane profit factor
            if m["profit_factor"] < 1.05:
                continue
            score = m["total_return_pct"] / max(m["max_dd_pct"], 1e-6)
            if score > best_score:
                best_score, best = score, (c, m)

        if best is None:
            print(f"fold {k+1}: no viable IS candidate")
            continue

        c, m_is = best
        p = replace(base, **c)
        m_oos = run_oos(oos_df, p)
        rows.append(
            dict(
                fold=k + 1,
                is_period=f"{is_df.index[0].date()}..{is_df.index[-1].date()}",
                oos_period=f"{oos_df.index[0].date()}..{oos_df.index[-1].date()}",
                **c,
                is_pf=round(m_is["profit_factor"], 2),
                is_ret=round(m_is["total_return_pct"], 1),
                is_dd=round(m_is["max_dd_pct"], 1),
                oos_pf=round(m_oos.get("profit_factor", 0), 2),
                oos_ret=round(m_oos.get("total_return_pct", 0), 1),
                oos_dd=round(m_oos.get("max_dd_pct", 0), 1),
                oos_trades=m_oos.get("trades", 0),
            )
        )
        print(
            f"fold {k+1}: params={c}\n"
            f"        IS  ret={m_is['total_return_pct']:7.1f}%  dd={m_is['max_dd_pct']:5.1f}%  pf={m_is['profit_factor']:.2f}\n"
            f"        OOS ret={m_oos.get('total_return_pct',0):7.1f}%  dd={m_oos.get('max_dd_pct',0):5.1f}%  pf={m_oos.get('profit_factor',0):.2f}  n={m_oos.get('trades',0)}"
        )

    if not rows:
        print("no completed folds")
        return 1

    res = pd.DataFrame(rows)
    os.makedirs(REPORT_DIR, exist_ok=True)
    res.to_csv(os.path.join(REPORT_DIR, f"walkforward_{args.tf}.csv"), index=False)

    oos_ret = res["oos_ret"]
    print("\n=== out-of-sample aggregate ===")
    print(f"  folds              : {len(res)}")
    print(f"  mean OOS return    : {oos_ret.mean():.1f}%")
    print(f"  median OOS return  : {oos_ret.median():.1f}%")
    print(f"  positive folds     : {(oos_ret > 0).sum()}/{len(res)}")
    print(f"  mean OOS PF        : {res['oos_pf'].mean():.2f}")
    print(f"  worst OOS dd       : {res['oos_dd'].max():.1f}%")
    print(f"\n  IS->OOS degradation : {(res['is_ret'].mean() - oos_ret.mean()):.1f} pts")
    print(f"  (a large gap here is the signature of curve-fitting)")
    print(f"\nsaved to {REPORT_DIR}/walkforward_{args.tf}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
