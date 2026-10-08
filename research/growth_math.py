#!/usr/bin/env python3
"""
The arithmetic of growing a tiny account on XAUUSD.

This is NOT a strategy and NOT a claim about any particular EA. It is the math
that has to hold for a small account to compound to a large one, so we can see
what is actually required instead of arguing about whether it is possible.

Two things dominate:

  1. Minimum position size. With a $3 account you cannot trade a smaller position
     than the broker's minimum lot. On gold that is typically 1 oz (0.01 lot).
     At $2000/oz a 1 oz position is ~$2000 of notional on a $3 account. Every
     $0.10 move in gold is ~3% of the account; a $1 move is ~33%. That leverage
     is what makes small-account growth possible at all - and it is also what
     makes ruin possible.

  2. Survival. The same leverage that grows the account can erase it. What
     matters is not "does it make money" but the ratio of P(reach target) to
     P(ruin), over many paths.

Usage:
    python3 research/growth_math.py --start 3 --target 5000 --oz 1 \
        --stop 0.30 --rr 1.5 --win 0.55 --paths 20000
    python3 research/growth_math.py --sweep
"""
from __future__ import annotations

import argparse

import numpy as np


def required_trades(start: float, target: float, per_trade_return: float) -> float:
    if per_trade_return <= 0:
        return float("inf")
    return np.log(target / start) / np.log(1 + per_trade_return)


def simulate(start: float, target: float, oz: float, stop: float, rr: float,
             win: float, risk_pct: float, paths: int, seed: int = 7,
             max_steps: int = 20000) -> dict:
    """Vectorised over paths.

    Position size is chosen to risk `risk_pct` of equity, but floored at the
    broker minimum lot (0.01 lot = `oz` ounces). That floor is the engine: on a
    tiny account the minimum lot risks MORE than the target percentage, so the
    early trades are over-leveraged and - if they survive - compound fast. As
    equity grows the floor stops binding and sizing becomes percentage-based.

    Ruin = equity no longer covers one minimum-lot stop.
    """
    rng = np.random.default_rng(seed)
    min_risk = stop * oz                      # $ risked by 1 minimum lot
    eq = np.full(paths, float(start))
    alive = np.ones(paths, bool)
    reached_at = np.full(paths, -1, dtype=np.int64)

    for step in range(1, max_steps + 1):
        active = alive & (eq < target) & (eq >= min_risk)
        if not active.any():
            break
        idx = np.flatnonzero(active)
        # lots as integer multiples of the minimum, targeting risk_pct of equity
        target_risk = eq[idx] * risk_pct / 100.0
        lots = np.maximum(1, np.floor(target_risk / min_risk + 0.5))
        risk = lots * min_risk
        won = rng.random(idx.size) < win
        eq[idx] += np.where(won, rr, -1.0) * risk
        just = idx[eq[idx] >= target]
        reached_at[just] = step
        alive[idx[eq[idx] < min_risk]] = False

    reached = reached_at >= 0
    ruined = ~reached          # includes those still climbing at the cap
    return {
        "P_reach": float(reached.mean()),
        "P_ruin": float(ruined.mean()),
        "median_trades_to_target": float(np.median(reached_at[reached])) if reached.any() else float("nan"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=3.0)
    ap.add_argument("--target", type=float, default=5000.0)
    ap.add_argument("--oz", type=float, default=1.0, help="position size (min lot in oz)")
    ap.add_argument("--stop", type=float, default=0.30, help="stop distance in $ per oz")
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--win", type=float, default=0.55)
    ap.add_argument("--risk-pct", type=float, default=3.0,
                    help="percent of equity risked once past the min-lot floor")
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--sweep", action="store_true", help="sweep win rate and R:R")
    args = ap.parse_args()

    risk = args.stop * args.oz
    print(f"account ${args.start:,.0f} -> ${args.target:,.0f}")
    print(f"position {args.oz} oz min lot, stop ${args.stop}/oz  =>  ${risk:.2f} risked per min lot")
    print(f"that min lot is {risk/args.start*100:.1f}% of the starting account")
    print(f"leverage feel: {args.oz*2000/args.start:.0f}x notional-to-equity at $2000/oz\n")

    if args.sweep:
        print(f"{'win':>5s} {'R:R':>5s} {'edge/trade':>11s} {'P(reach)':>9s} {'P(ruin)':>8s} {'trades':>8s}")
        for win in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
            for rr in (1.0, 1.5, 2.0, 3.0):
                edge = win * rr - (1 - win)
                s = simulate(args.start, args.target, args.oz, args.stop, rr, win,
                             args.risk_pct, args.paths)
                print(f"{win:5.2f} {rr:5.1f} {edge:+11.3f} {s['P_reach']*100:8.1f}% "
                      f"{s['P_ruin']*100:7.1f}% {s['median_trades_to_target']:8.0f}")
        print("\nedge/trade is in units of the money risked (R). Positive is required.")
        print("A positive edge alone is not enough - the early leverage decides survival.")
        return 0

    s = simulate(args.start, args.target, args.oz, args.stop, args.rr, args.win,
                 args.risk_pct, args.paths)
    edge = args.win * args.rr - (1 - args.win)
    print(f"edge per trade : {edge:+.3f} R")
    print(f"P(reach target): {s['P_reach']*100:.1f}%")
    print(f"P(ruin)        : {s['P_ruin']*100:.1f}%")
    print(f"median trades  : {s['median_trades_to_target']:.0f}")
    if s["P_reach"] > 0:
        print(f"odds (reach:ruin) = {s['P_reach']/max(s['P_ruin'],1e-9):.2f} : 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
