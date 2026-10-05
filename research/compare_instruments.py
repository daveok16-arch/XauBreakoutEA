#!/usr/bin/env python3
"""
Diagnostic comparison of two gold datasets (e.g. spot XAUUSD vs COMEX GC).

STRICTLY DIAGNOSTIC. This tool explains *why* an import may be inconclusive. It
never grants a pass and is never consulted by the production gate.

The point: spot and futures do not need identical prices for breakout research to
transfer. What matters is whether their breakouts, volatility, ATR behaviour and
resulting signals are similar. So this reports both:

  A. price-level relationship   (basis - informative, not decisive)
  B. structural equivalence     (returns, OHLC direction, session structure)
  C. signal equivalence         (Donchian breakouts, timing, ATR, stops, trades)

Only C (with B) tells you whether the futures baseline can validate a Deriv EA.

Usage:
    python3 research/compare_instruments.py --csv path/XAUUSD_H1.csv
    python3 research/compare_instruments.py --csv spot.csv --against futures.csv
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
import strategy
from strategy import Params

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
OHLC = ["Open", "High", "Low", "Close"]


def _basis_block(a: pd.DataFrame, b: pd.DataFrame, common: pd.DatetimeIndex, label_a, label_b):
    """Price-level basis over common timestamps. Informative, not decisive."""
    ca = a.loc[common, "Close"].to_numpy()
    cb = b.loc[common, "Close"].to_numpy()
    basis = ca - cb
    basis_pct = basis / cb * 100.0
    print(f"\n--- A. price-level basis ({label_a} - {label_b}) ---")
    print(f"  common timestamps        : {len(common)}")
    print(f"  basis abs (mean)         : {basis.mean():+.2f}")
    print(f"  basis % of {label_b:8s}  : mean {basis_pct.mean():+.3f}%  "
          f"median {np.median(basis_pct):+.3f}%")
    print(f"  basis % std              : {basis_pct.std():.3f}%")
    print(f"  basis % P5 / P95         : {np.percentile(basis_pct,5):+.3f}% / "
          f"{np.percentile(basis_pct,95):+.3f}%")
    print(f"  max |basis %|            : {np.abs(basis_pct).max():.3f}%")
    # stability through time: does the basis drift?
    q = np.array_split(basis_pct, 4)
    print(f"  basis % by quartile      : " + "  ".join(f"{x.mean():+.3f}" for x in q))
    return basis_pct


def _coverage_block(a, b, common, label_a, label_b):
    print(f"\n--- timestamp coverage ---")
    print(f"  {label_a:10s}: {len(a)} bars  {a.index.min()} .. {a.index.max()}")
    print(f"  {label_b:10s}: {len(b)} bars  {b.index.min()} .. {b.index.max()}")
    lo = max(a.index.min(), b.index.min())
    hi = min(a.index.max(), b.index.max())
    print(f"  overlap window           : {lo} .. {hi}")
    print(f"  common timestamps        : {len(common)}")
    only_a = a.loc[(a.index >= lo) & (a.index <= hi)].index.difference(common)
    only_b = b.loc[(b.index >= lo) & (b.index <= hi)].index.difference(common)
    print(f"  in {label_a} only{' '*3}: {len(only_a)}")
    print(f"  in {label_b} only{' '*3}: {len(only_b)}")


def _structure_block(a, b, common, label_a, label_b):
    """Return and OHLC-direction equivalence - the part that actually matters."""
    print(f"\n--- B. return / structure equivalence ---")
    ca = a.loc[common, "Close"].to_numpy()
    cb = b.loc[common, "Close"].to_numpy()
    ra = np.diff(ca) / ca[:-1]
    rb = np.diff(cb) / cb[:-1]
    corr_ret = np.corrcoef(ra, rb)[0, 1] if len(ra) > 2 else float("nan")
    corr_px = np.corrcoef(ca, cb)[0, 1] if len(ca) > 2 else float("nan")
    print(f"  price correlation        : {corr_px:.6f}")
    print(f"  RETURN correlation       : {corr_ret:.6f}   <- the one that matters")
    sign_agree = (np.sign(ra) == np.sign(rb)).mean() * 100
    print(f"  return sign agreement    : {sign_agree:.2f}%")

    # OHLC directional agreement: same up/down bar, and same intrabar direction
    da = np.sign(a.loc[common, "Close"].to_numpy() - a.loc[common, "Open"].to_numpy())
    db = np.sign(b.loc[common, "Close"].to_numpy() - b.loc[common, "Open"].to_numpy())
    bar_agree = (da == db).mean() * 100
    print(f"  bar direction agreement  : {bar_agree:.2f}%")

    # session / time-of-day structure in the basis
    print(f"\n--- basis by hour (session structure) ---")
    bp = pd.Series((ca - cb) / cb * 100.0, index=common)
    by_hour = bp.groupby(bp.index.hour).mean()
    hours = by_hour.index.tolist()
    vals = "  ".join(f"{h:02d}:{v:+.2f}" for h, v in zip(hours, by_hour.values))
    print(f"  {vals}")
    spread_h = by_hour.max() - by_hour.min()
    print(f"  hour-to-hour basis range : {spread_h:.3f}% "
          f"({'persistent session structure' if spread_h > 0.1 else 'no material session structure'})")
    return corr_ret, sign_agree, bar_agree


def _signal_block(a, b, common, p: Params, label_a, label_b):
    """Run the SAME Donchian logic on both and compare the resulting signals."""
    import h4 as h4mod
    from strategy import atr_wilder

    print(f"\n--- C. Donchian signal equivalence ---")

    # remap plans onto timestamps, then keep only common timestamps
    sa = {a.index[i]: v for i, v in h4mod.h1_entry_plan(a, p).items() if a.index[i] in common}
    sb = {b.index[i]: v for i, v in h4mod.h1_entry_plan(b, p).items() if b.index[i] in common}
    ta, tb = set(sa), set(sb)
    inter = ta & tb

    print(f"  signals {label_a:10s}       : {len(sa)}")
    print(f"  signals {label_b:10s}       : {len(sb)}")
    print(f"  same timestamp            : {len(inter)}")
    if ta and tb:
        print(f"  breakout Jaccard overlap  : {len(inter)/len(ta|tb)*100:.1f}%")
    dir_agree = sum(1 for t in inter if sa[t][0] == sb[t][0])
    if inter:
        print(f"  entry-direction agreement : {dir_agree/len(inter)*100:.1f}% "
              f"({dir_agree}/{len(inter)})")

    # signal timestamp displacement: nearest signal on the other series
    if ta and tb:
        arr_b = np.array(sorted(tb), dtype="datetime64[ns]")
        arr_a = np.array(sorted(ta), dtype="datetime64[ns]")
        disp = []
        for t in arr_a:
            j = np.searchsorted(arr_b, t)
            cands = [k for k in (j - 1, j) if 0 <= k < len(arr_b)]
            if cands:
                disp.append(min(abs((arr_b[k] - t) / np.timedelta64(1, "h")) for k in cands))
        disp = np.array(disp)
        print(f"  signal displacement (h)   : median {np.median(disp):.1f}  "
              f"mean {disp.mean():.1f}  <=1h {np.mean(disp<=1)*100:.0f}%")

    # ATR and stop-distance ratios (stop = stop_atr x ATR, so ratios coincide)
    ra = (atr_wilder(a, p.atr_period).loc[common] /
          atr_wilder(b, p.atr_period).loc[common]).dropna()
    print(f"  ATR ratio (a/b)          : mean {ra.mean():.3f}  median {ra.median():.3f}  "
          f"std {ra.std():.3f}  P5 {np.percentile(ra,5):.3f}  P95 {np.percentile(ra,95):.3f}")
    print(f"  stop-distance ratio      : {ra.mean():.3f} (same as ATR ratio, stop = "
          f"{p.stop_atr}x ATR)")

    # trade-level agreement
    _, trades_a, _ = strategy.backtest(a, p)
    _, trades_b, _ = strategy.backtest(b, p)
    ea = {t.entry_time: t.side for t in trades_a}
    eb = {t.entry_time: t.side for t in trades_b}
    cmn = set(ea) & set(eb)
    if ea and eb:
        print(f"  trades {label_a:10s}       : {len(ea)}")
        print(f"  trades {label_b:10s}       : {len(eb)}")
        print(f"  identical entries         : {len(cmn)}  "
              f"({len(cmn)/max(len(ea),len(eb))*100:.1f}% of larger)")
        if cmn:
            sd = sum(1 for t in cmn if ea[t] == eb[t])
            print(f"  identical entry direction : {sd/len(cmn)*100:.1f}%")

    return dict(signals_a=len(sa), signals_b=len(sb), common_signals=len(inter),
                direction_agreement=(dir_agree/len(inter)*100) if inter else 0.0)


def compare(a, b, p: Params, label_a, label_b, tf="h1") -> dict:
    common = a.index.intersection(b.index)
    if len(common) < 30:
        print(f"only {len(common)} common timestamps - too few to compare")
        return {"common_timestamps": len(common)}
    _coverage_block(a, b, common, label_a, label_b)
    basis_pct = _basis_block(a, b, common, label_a, label_b)
    corr_ret, sign_agree, bar_agree = _structure_block(a, b, common, label_a, label_b)
    sig = _signal_block(a, b, common, p, label_a, label_b)

    metrics = dict(
        common_timestamps=len(common),
        basis_pct_mean=float(np.mean(basis_pct)),
        basis_pct_std=float(np.std(basis_pct)),
        return_correlation=float(corr_ret),
        return_sign_agreement=float(sign_agree),
        bar_direction_agreement=float(bar_agree),
        **sig,
    )

    print("\n=== interpretation (diagnostic only) ===")
    verdict = [
        ("returns highly correlated", corr_ret > 0.95),
        ("bar direction agrees >95%", bar_agree > 95),
        ("breakout direction agrees >90%", sig["direction_agreement"] > 90),
    ]
    for name, ok in verdict:
        print(f"  [{'yes' if ok else ' no'}] {name}")
    equivalent = all(ok for _, ok in verdict)
    metrics["structurally_equivalent"] = equivalent
    if equivalent:
        print("  -> structure and signals look equivalent; the futures baseline is")
        print("     probably usable for research validation despite the price basis.")
    else:
        print("  -> material structural differences. Do NOT use the futures-derived")
        print("     baseline to validate the Deriv EA; the instruments break out at")
        print("     different times.")
    print("  NOTE: diagnostic only. This never changes a gate result.")
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="the dataset to compare (e.g. spot)")
    ap.add_argument("--against", help="reference dataset CSV; default = cached H1")
    ap.add_argument("--tf", default="h1")
    ap.add_argument("--shift-hours", type=float, default=0.0)
    args = ap.parse_args()

    a, rep = deriv_csv.load_csv(args.csv, shift_hours=args.shift_hours)
    print(deriv_csv.format_report(rep))
    if args.against:
        b, repb = deriv_csv.load_csv(args.against)
        print(deriv_csv.format_report(repb))
        label_b = os.path.basename(args.against)
    else:
        b = fetch_data.load(args.tf)
        label_b = f"cached-{args.tf} (COMEX GC=F proxy)"

    p = Params(spread=0.30, commission_per_side=0.0)
    compare(a, b, p, os.path.basename(args.csv), label_b, args.tf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
