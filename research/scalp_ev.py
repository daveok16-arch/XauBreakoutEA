#!/usr/bin/env python3
"""
EV math for a fast scalper with balance-tiered lot sizing.

Mechanism (as described):
  - start at the broker minimum lot on a small account
  - as the account grows, step the lot size up in levels (balance tiers)
  - scalp fast: many trades, very short holds

Balance-tiered sizing is COMPOUNDING (size tracks equity), not recovery
martingale (size tracks losses). The two are different, and this tool is about
the first.

The crux of any scalper is one number: the break-even win rate after spread.
Here is why. Over one trade, with take-profit TP, stop-loss SL, and a round-trip
spread cost s (in the same units), spread is paid on every trade:

    net win  = TP - s
    net loss = SL + s
    break-even p* solves  p*(TP - s) = (1 - p)*(SL + s)

    p* = (SL + s) / (TP + SL)

If p* is high and the mechanism's win rate is near it, the edge is fragile. If p*
is above the achievable win rate, the scalper loses no matter how it sizes.

Tiered sizing only changes HOW FAST you compound; the sign of the per-trade edge
decides whether you compound or bleed.

Usage:
    python3 research/scalp_ev.py --tp 0.5 --sl 0.5 --spread 0.25
    python3 research/scalp_ev.py --table
    python3 research/scalp_ev.py --sim --tp 0.3 --sl 1.0 --spread 0.25 --win 0.80
"""
from __future__ import annotations

import argparse

import numpy as np


def breakeven_win(tp: float, sl: float, spread: float) -> float:
    """Win rate required just to break even, spread included."""
    num = sl + spread
    den = tp + sl
    return num / den if den > 0 else float("nan")


def edge_per_trade(tp: float, sl: float, spread: float, win: float) -> float:
    """Expected P&L per trade in price units (positive = profitable)."""
    return win * (tp - spread) - (1 - win) * (sl + spread)


def simulate(start: float, tiers: list[tuple[float, float]], tp: float, sl: float,
             spread: float, win: float, oz_per_lot: float, trades_per_day: int,
             days: int, paths: int, seed: int = 7, ruin_frac: float = 0.5,
             target: float | None = None) -> dict:
    """Compounding scalper with balance-tiered lots, spread on every trade.

    tiers: list of (balance_threshold, lot_size) ascending. Lot is the largest
    tier whose threshold <= equity. Ruin = equity falls below ruin_frac * start.
    If `target` is given, also reports P(reach target) and median trades to it.
    """
    rng = np.random.default_rng(seed)
    thresholds = np.array([t[0] for t in tiers], float)
    lots = np.array([t[1] for t in tiers], float)
    n_trades = trades_per_day * days
    eq = np.full(paths, float(start))
    peak = eq.copy()
    max_dd = np.zeros(paths)
    ruin = np.zeros(paths, bool)
    ruin_at = np.full(paths, -1, dtype=np.int64)
    reach_at = np.full(paths, -1, dtype=np.int64)
    floor = ruin_frac * start

    for k in range(1, n_trades + 1):
        active = ~ruin
        if not active.any():
            break
        idx = np.flatnonzero(active)
        # lot for the current equity tier
        tier = np.searchsorted(thresholds, eq[idx], side="right") - 1
        tier = np.clip(tier, 0, len(lots) - 1)
        lot = lots[tier]
        scale = lot * oz_per_lot                       # $ per 1.0 price move
        risk = (sl + spread) * scale
        reward = (tp - spread) * scale
        won = rng.random(idx.size) < win
        eq[idx] += np.where(won, reward, -risk)
        peak[idx] = np.maximum(peak[idx], eq[idx])
        dd = (peak[idx] - eq[idx]) / np.maximum(peak[idx], 1e-9)
        max_dd[idx] = np.maximum(max_dd[idx], dd)
        if target is not None:
            just = idx[(eq[idx] >= target) & (reach_at[idx] < 0)]
            reach_at[just] = k
        newly = idx[eq[idx] <= floor]
        ruin[newly] = True
        ruin_at[newly] = k

    out = {
        "final_median": float(np.median(eq)),
        "final_p10": float(np.percentile(eq, 10)),
        "final_p90": float(np.percentile(eq, 90)),
        "P_ruin": float(ruin.mean()),
        "median_max_dd": float(np.median(max_dd) * 100),
    }
    if target is not None:
        reached = reach_at >= 0
        out["P_reach"] = float(reached.mean())
        out["median_trades_to_target"] = (
            float(np.median(reach_at[reached])) if reached.any() else float("nan"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tp", type=float, default=0.5)
    ap.add_argument("--sl", type=float, default=0.5)
    ap.add_argument("--spread", type=float, default=0.25)
    ap.add_argument("--win", type=float, default=0.60)
    ap.add_argument("--start", type=float, default=10.0)
    ap.add_argument("--oz-per-lot", type=float, default=1.0)
    ap.add_argument("--trades-per-day", type=int, default=50)
    ap.add_argument("--days", type=int, default=250)
    ap.add_argument("--paths", type=int, default=5000)
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--broker", metavar="FILE",
                    help="MT5 key=value spec file; overrides --spread with the detected cost")
    args = ap.parse_args()

    if args.broker:
        from broker_profile import BrokerProfile
        bp = BrokerProfile.from_mt5_kv(open(args.broker).read())
        print(bp.summary())
        args.spread = bp.round_trip_cost_price
        args.oz_per_lot = bp.contract_size
        print(f"using detected round-trip cost = {args.spread:.4f} price\n")

    if args.table:
        print("Break-even win rate after spread (higher = harder)")
        print(f"{'TP':>5s} {'SL':>5s} | " + "  ".join(f"spread={s:<5g}" for s in (0.10, 0.20, 0.30, 0.50)))
        for tp in (0.2, 0.3, 0.5, 1.0, 2.0):
            for sl in (0.5, 1.0, 2.0):
                row = "  ".join(f"{breakeven_win(tp, sl, s)*100:9.1f}%" for s in (0.10, 0.20, 0.30, 0.50))
                print(f"{tp:5.1f} {sl:5.1f} | {row}")
        print("\nRead it as: 'to profit with TP=X, SL=Y, spread=Z, you must win more than this %'.")
        print("Tight TP + wide spread pushes the required win rate toward and past 100%.")
        return 0

    pstar = breakeven_win(args.tp, args.sl, args.spread)
    e = edge_per_trade(args.tp, args.sl, args.spread, args.win)
    print(f"scalp: TP {args.tp}, SL {args.sl}, spread {args.spread}, win {args.win:.0%}")
    print(f"  break-even win rate : {pstar*100:.1f}%")
    print(f"  edge per trade      : {e:+.4f} price units "
          f"({e/(args.sl+args.spread)*100:+.2f}% of risked $)")

    if not args.sim:
        if args.win > pstar:
            print("  -> positive edge; tiered sizing will compound it.")
        else:
            print("  -> win rate at/below break-even; no sizing scheme saves it.")
        return 0

    tiers = [(0, 0.01), (25, 0.02), (50, 0.03), (100, 0.05), (250, 0.10), (500, 0.20)]
    s = simulate(args.start, tiers, args.tp, args.sl, args.spread, args.win,
                 args.oz_per_lot, args.trades_per_day, args.days, args.paths)
    print(f"\n  simulate ${args.start:.0f}, {args.trades_per_day}/day x {args.days} days "
          f"({args.trades_per_day*args.days} scalps), tiered lots {[t[1] for t in tiers]}")
    print(f"  median final : ${s['final_median']:,.2f}   (p10 ${s['final_p10']:,.2f}, p90 ${s['final_p90']:,.2f})")
    print(f"  P(ruin, >=50% loss): {s['P_ruin']*100:.1f}%")
    print(f"  median max drawdown: {s['median_max_dd']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
