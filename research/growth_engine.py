#!/usr/bin/env python3
"""
The growth engine: lot size levelling up AND trade count rising as the account
grows, run on our PROVEN edge.

This is the mechanism the user described, stated mechanically:

    equity up  ->  lot size steps up a level      (bigger position per trade)
    equity up  ->  more trades fire               (more channels / concurrent slots)
    both       ->  equity moves faster            (positive feedback)

Two things must be separated, because they are NOT the same:

  A. Lot levelling. This is just compounding. Fixed-fraction sizing already does
     it continuously; discrete "levels" are a coarser version of the same thing.
     On a tiny account the broker MINIMUM lot binds first, which forces risk% to
     be very high (a $12 micro account risks ~15% on the min lot). As equity
     grows the floor stops binding and risk% falls to target, then lots step up.

  B. Trade scaling. Firing more trades as equity grows adds frequency - the lever
     the frequency bridge showed actually moves the needle. But more concurrent
     trades also means more risk open at once, so it scales RUIN along with
     growth. The disciplined version scales slowly.

We simulate both on the real per-trade R pool of the proven long-only edge, so
the result is not an assumption about edge - it is our edge, compounded.

Usage:
    python3 research/growth_engine.py
    python3 research/growth_engine.py --tf h1 --lookback 5 --scale-trades
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import numpy as np

import fetch_data
import strategy


def simulate(R_pool: np.ndarray, start: float, target: float, tpy0: float,
             risk0: float, minlot_risk: float, paths: int = 20000, seed: int = 7,
             scale_trades: bool = False, scale_pow: float = 0.5,
             scale_max: float = 8.0, ruin_frac: float = 0.5,
             max_steps: int = 200000) -> dict:
    """Bootstrap the real R pool forward.

    risk% per trade = max(risk0, minlot_risk/equity)  -> lot floor binds small,
    then continuous levelling to target.
    trades/yr       = tpy0 * min(scale_max, (equity/start)**scale_pow) if scaling.
    Time is tracked per trade (1/tpy years each), so scaling changes the calendar.
    """
    rng = np.random.default_rng(seed)
    eq = np.full(paths, float(start))
    yrs = np.zeros(paths)
    reached = np.zeros(paths, bool)
    ruined = np.zeros(paths, bool)
    reach_yr = np.full(paths, np.nan)
    peak = eq.copy()
    max_dd = np.zeros(paths)

    for _ in range(max_steps):
        active = ~(reached | ruined)
        if not active.any():
            break
        idx = np.flatnonzero(active)
        e = eq[idx]
        rf = np.maximum(risk0, minlot_risk / e)
        tpy = np.full(idx.size, tpy0)
        if scale_trades:
            tpy = tpy0 * np.minimum(scale_max, np.maximum(1.0, (e / start) ** scale_pow))
        yrs[idx] += 1.0 / tpy

        r = rng.choice(R_pool, size=idx.size)
        eq[idx] = np.maximum(e * (1.0 + rf * r), 0.0)
        peak[idx] = np.maximum(peak[idx], eq[idx])
        max_dd[idx] = np.maximum(max_dd[idx], (peak[idx] - eq[idx]) / np.maximum(peak[idx], 1e-9))

        just = idx[(eq[idx] >= target) & ~reached[idx]]
        reached[just] = True
        reach_yr[just] = yrs[just]
        dead = idx[(eq[idx] <= ruin_frac * start) & ~ruined[idx]]
        ruined[dead] = True

    return {
        "P_reach": float(reached.mean()),
        "P_ruin": float(ruined.mean()),
        "median_years": float(np.nanmedian(reach_yr)) if reached.any() else float("nan"),
        "p10_years": float(np.nanpercentile(reach_yr, 10)) if reached.any() else float("nan"),
        "median_max_dd": float(np.median(max_dd) * 100),
    }


def edge_pool(tf: str, lookback: int) -> tuple[np.ndarray, float]:
    df = fetch_data.load(tf)
    years = (df.index[-1] - df.index[0]).days / 365.25
    _, trades, _ = strategy.backtest(
        df, replace(strategy.Params(), allow_short=False, lookback=lookback))
    r = np.array([t.r_multiple for t in trades])
    return r, len(r) / years


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1"])
    ap.add_argument("--lookback", type=int, default=60)
    ap.add_argument("--start", type=float, default=12.0)
    ap.add_argument("--target", type=float, default=5000.0)
    ap.add_argument("--risk", type=float, default=0.75, help="target %% risk once past the lot floor")
    ap.add_argument("--minlot-risk", type=float, default=1.86,
                    help="$ risked by one minimum lot (micro gold ~1.86)")
    ap.add_argument("--scale-trades", action="store_true")
    ap.add_argument("--paths", type=int, default=20000)
    args = ap.parse_args()

    r, tpy = edge_pool(args.tf, args.lookback)
    print(f"edge: {args.tf} N={args.lookback}  {len(r)} trades, {tpy:.1f}/yr, "
          f"avgR {r.mean():+.3f}, win {(r>0).mean()*100:.0f}%")
    print(f"account ${args.start:.0f} -> ${args.target:,.0f}, target risk {args.risk}%, "
          f"min-lot risk ${args.minlot_risk:.2f}\n")

    print(f"{'engine':>26s} {'P(reach)':>9s} {'P(ruin)':>8s} {'median yrs':>11s} {'p10 yrs':>8s} {'medDD%':>7s}")
    for label, scale in [("lot levelling only", False), ("lot levelling + trade scaling", True)]:
        s = simulate(r, args.start, args.target, tpy, args.risk / 100.0,
                     args.minlot_risk, paths=args.paths, scale_trades=scale)
        print(f"{label:>26s} {s['P_reach']*100:8.1f}% {s['P_ruin']*100:7.1f}% "
              f"{s['median_years']:11.1f} {s['p10_years']:8.1f} {s['median_max_dd']:7.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
