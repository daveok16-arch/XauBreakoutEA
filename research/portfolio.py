#!/usr/bin/env python3
"""
Multi-timeframe portfolio: H1 and H4 breakout legs under one shared risk budget.

Both legs trade the *same* breakout edge on gold, so they are correlated, not
independent. This engine therefore:

  - runs both legs on one H1 timeline,
  - caps the COMBINED open risk at a shared budget (not one budget per leg),
  - records, for every trade, how many same-direction positions were open at the
    same time, so the overlap (and the double-counted edge) can be measured.

Timing and costs are realistic:
  - H4 signals use only completed H4 candles and enter at the next H1 open,
  - all entries pay half-spread + commission,
  - exits use the same bar-level stop/TP/trailing rules as strategy.py.

Variants (identical data, costs and risk):
  1. h1_only          - the production leg alone
  2. h4_only          - the new leg alone
  3. combined         - both, one shared risk budget
  4. combined_indep   - both, one budget per leg (the naive, risk-doubling case)

Usage:
    python3 research/portfolio.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

import fetch_data
import h4 as h4mod
import strategy
from strategy import Params, Trade, manage_bar

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

DERIV = dict(spread=0.30, commission_per_side=0.0)


def _simulate(df, p, plans, shared_budget: bool):
    """plans: {leg_name: {bar_index: (side, atr, stop_dist)}}."""
    n = len(df)
    idx = df.index
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    openp = df["Open"].to_numpy()
    close = df["Close"].to_numpy()
    half_spread = p.spread / 2.0
    cost_per_side = half_spread + p.commission_per_side

    legs = list(plans.keys())
    equity = p.start_equity
    peak = equity
    max_dd = 0.0
    curve = np.full(n, np.nan)
    trades: list[Trade] = []
    open_pos: dict[str, dict] = {}

    def close_pos(leg, bar_i, price, reason):
        nonlocal equity
        pos = open_pos.pop(leg)
        gross = (price - pos["entry"]) * pos["size"] if pos["side"] == "long" \
            else (pos["entry"] - price) * pos["size"]
        net = gross - cost_per_side * pos["size"]
        equity += net
        trades.append(Trade(
            side=pos["side"], entry_time=pos["entry_time"], entry=pos["entry"],
            exit_time=idx[bar_i], exit=price, size=pos["size"], pnl=net,
            r_multiple=net / pos["risk_money"] if pos["risk_money"] else 0.0,
            reason=reason, bars_held=bar_i - pos["entry_bar"], leg=leg,
        ))

    for i in range(n):
        # ---- manage open positions (all legs) --------------------------
        for leg in list(open_pos.keys()):
            hit = manage_bar(open_pos[leg], i, high, low, p)
            if hit is not None:
                close_pos(leg, i, hit[0], hit[1])

        # ---- entries ---------------------------------------------------
        for leg in legs:
            if leg in open_pos:
                continue
            entry = plans[leg].get(i)
            if entry is None:
                continue
            side, atr, stop_dist = entry
            if stop_dist <= 0:
                continue
            risk_pct = p.risk_pct
            if shared_budget:
                used = sum(pos["risk_money"] for pos in open_pos.values()) / equity * 100.0
                remaining = max(0.0, p.max_total_risk_pct - used)
                risk_pct = min(risk_pct, remaining)
            if risk_pct <= 0:
                continue
            entry_px = openp[i] + (half_spread if side == "long" else -half_spread)
            sl = entry_px - stop_dist if side == "long" else entry_px + stop_dist
            tp = (entry_px + p.reward_risk * stop_dist if side == "long"
                  else entry_px - p.reward_risk * stop_dist)
            risk_money = equity * risk_pct / 100.0
            size = risk_money / stop_dist
            equity -= cost_per_side * size
            open_pos[leg] = dict(
                side=side, entry=entry_px, init_sl=sl, sl=sl, tp=tp, size=size,
                atr=atr, entry_bar=i, entry_time=idx[i], risk_money=risk_money,
                hw=entry_px, lw=entry_px, tp_on=True, ttp_on=False, ttp=0.0,
                leg=leg,
            )

        # ---- mark to market --------------------------------------------
        unreal = 0.0
        for pos in open_pos.values():
            unreal += (close[i] - pos["entry"]) * pos["size"] if pos["side"] == "long" \
                else (pos["entry"] - close[i]) * pos["size"]
        mark = equity + unreal
        curve[i] = mark
        peak = max(peak, mark)
        max_dd = max(max_dd, (peak - mark) / peak if peak > 0 else 0.0)

    for leg in list(open_pos.keys()):
        close_pos(leg, n - 1, close[n - 1], "eod")

    curve = pd.Series(curve, index=idx).ffill()
    return curve, trades, max_dd


def overlap_stats(trades: list[Trade]) -> dict:
    """How often were two same-direction positions open at once?"""
    if not trades:
        return {}
    ivs = [(t.entry_time, t.exit_time, t.side, t.leg) for t in trades]
    both = same_dir = opp_dir = 0
    for a in range(len(ivs)):
        for b in range(a + 1, len(ivs)):
            s1, e1, d1, l1 = ivs[a]
            s2, e2, d2, l2 = ivs[b]
            if l1 == l2:
                continue
            if s1 <= e2 and s2 <= e1:      # intervals overlap
                both += 1
                if d1 == d2:
                    same_dir += 1
                else:
                    opp_dir += 1
    return {
        "overlapping_pairs": both,
        "same_direction": same_dir,
        "opposite_direction": opp_dir,
        "same_dir_share_pct": (same_dir / both * 100) if both else 0.0,
    }


def budget_sweep(h1, plans, base):
    """Show what the shared budget actually does by making it bind."""
    print("\n=== shared-budget sensitivity (combined) ===")
    print(f"  {'max_total_risk%':>16s} {'CAGR%':>7s} {'maxDD%':>7s} {'PF':>6s} {'trades':>7s}")
    rows = []
    for cap in (0.75, 1.0, 1.5, 2.0, 3.0):
        p = replace(base, max_total_risk_pct=cap)
        curve, trades, dd = _simulate(h1, p, plans, True)
        m = strategy.metrics(curve, trades, dd, p)
        print(f"  {cap:16.2f} {m['cagr_pct']:7.1f} {m['max_dd_pct']:7.1f} "
              f"{m['profit_factor']:6.2f} {m['trades']:7d}")
        rows.append(dict(max_total_risk_pct=cap, **{k: m[k] for k in
                    ("cagr_pct", "max_dd_pct", "profit_factor", "trades")}))
    return pd.DataFrame(rows)


def oos_segments(h1, plans_map, base, folds=6):
    """Fixed-parameter segments. Params fixed a priori, so each segment is unseen."""
    print(f"\n=== fixed-parameter out-of-sample segments ({folds}) ===")
    n = len(h1)
    size = n // folds
    rows = []
    for k in range(folds):
        lo, hi = k * size, (k + 1) * size
        seg = h1.iloc[lo:hi]
        row = dict(seg=k + 1, period=f"{seg.index[0].date()}..{seg.index[-1].date()}")
        for name, plans in plans_map.items():
            sub = {leg: {i - lo: v for i, v in pl.items() if lo <= i < hi}
                   for leg, pl in plans.items()}
            curve, trades, dd = _simulate(seg, base, sub, True)
            m = strategy.metrics(curve, trades, dd, base)
            row[f"{name}_ret"] = m.get("total_return_pct", 0)
            row[f"{name}_dd"] = m.get("max_dd_pct", 0)
        rows.append(row)
    res = pd.DataFrame(rows)
    cols = list(plans_map.keys())
    print(f"  {'seg':>3s} {'period':24s} " + " ".join(f"{c+'_ret':>12s}" for c in cols))
    for _, r in res.iterrows():
        print(f"  {r.seg:3d} {r.period:24s} " +
              " ".join(f"{r[c+'_ret']:12.1f}" for c in cols))
    for c in cols:
        rr = res[c + "_ret"]
        print(f"  {c:9s}: mean={rr.mean():6.1f}%  positive={int((rr>0).sum())}/{len(rr)}")
    return res


def run_tf(base_tf: str, htf_rule: str, folds: int) -> int:
    """Run the four variants on a given base/HTF pair.

    base_tf 'h1' -> H4 leg (short, recent window); base_tf 'daily' -> weekly leg
    (26 years, multiple regimes). Same engine, same costs, same risk.
    """
    base = fetch_data.load(base_tf)
    htf = h4mod.resample_tf(base, htf_rule)
    p = Params(**DERIV)
    plan_base = h4mod.h1_entry_plan(base, p)
    plan_htf = h4mod.entry_plan(base, htf, p)

    print(f"\n########## base={base_tf}  htf={htf_rule} ##########")
    print(f"base {base.index.min().date()}..{base.index.max().date()}  {len(base)} bars")
    print(f"htf  {htf.index.min().date()}..{htf.index.max().date()}  {len(htf)} bars "
          f"({len(plan_htf)} signals)")

    variants = {
        f"{base_tf}_only": ({base_tf.upper(): plan_base}, True),
        f"{htf_rule}_only": ({htf_rule.upper(): plan_htf}, True),
        "combined_shared": ({base_tf.upper(): plan_base, htf_rule.upper(): plan_htf}, True),
        "combined_indep": ({base_tf.upper(): plan_base, htf_rule.upper(): plan_htf}, False),
    }

    rows, all_trades = [], {}
    for name, (plans, shared) in variants.items():
        curve, trades, dd = _simulate(base, p, plans, shared)
        m = strategy.metrics(curve, trades, dd, p)
        m["variant"] = name
        rows.append(m)
        all_trades[name] = trades
        print(f"\n=== {name} ===")
        print(f"  trades={m['trades']}  CAGR={m['cagr_pct']:.1f}%  net={m['total_return_pct']:.1f}%  "
              f"maxDD={m['max_dd_pct']:.1f}%  PF={m['profit_factor']:.2f}  "
              f"win/loss={m['avg_win_loss_ratio']:.2f}  win%={m['win_rate']:.1f}")

    comb = all_trades["combined_shared"]
    ov = overlap_stats(comb)
    print(f"\n=== trade overlap (combined_shared) ===")
    print(f"  overlapping pairs={ov.get('overlapping_pairs',0)}  "
          f"same dir={ov.get('same_direction',0)} ({ov.get('same_dir_share_pct',0):.1f}%)  "
          f"opp dir={ov.get('opposite_direction',0)}")

    segs = oos_segments(base, {f"{base_tf}_only": {base_tf.upper(): plan_base},
                               f"{htf_rule}_only": {htf_rule.upper(): plan_htf},
                               "combined": {base_tf.upper(): plan_base, htf_rule.upper(): plan_htf}},
                        p, folds=folds)
    pd.DataFrame([{k: v for k, v in r.items() if k != "exits"} for r in rows]).to_csv(
        os.path.join(REPORT_DIR, f"portfolio_variants_{base_tf}.csv"), index=False)
    segs.to_csv(os.path.join(REPORT_DIR, f"portfolio_oos_{base_tf}.csv"), index=False)
    return 0


def main() -> int:
    os.makedirs(REPORT_DIR, exist_ok=True)
    h1 = fetch_data.load("h1")
    h4 = h4mod.resample_h4(h1)
    p = Params(**DERIV)

    plan_h1 = h4mod.h1_entry_plan(h1, p)
    plan_h4 = h4mod.entry_plan(h1, h4, p)

    print(f"H1 {h1.index.min().date()}..{h1.index.max().date()}  {len(h1)} bars")
    print(f"H4 {h4.index.min().date()}..{h4.index.max().date()}  {len(h4)} bars "
          f"(resampled, {len(plan_h4)} signals)")

    variants = {
        "1_h1_only": ({"H1": plan_h1}, True),
        "2_h4_only": ({"H4": plan_h4}, True),
        "3_combined_shared": ({"H1": plan_h1, "H4": plan_h4}, True),
        "4_combined_indep": ({"H1": plan_h1, "H4": plan_h4}, False),
    }

    rows = []
    all_trades = {}
    for name, (plans, shared) in variants.items():
        curve, trades, dd = _simulate(h1, p, plans, shared)
        m = strategy.metrics(curve, trades, dd, p)
        m["variant"] = name
        rows.append(m)
        all_trades[name] = trades
        print(f"\n=== {name} ===")
        print(f"  trades={m['trades']}  CAGR={m['cagr_pct']:.1f}%  net={m['total_return_pct']:.1f}%  "
              f"maxDD={m['max_dd_pct']:.1f}%  PF={m['profit_factor']:.2f}  "
              f"win/loss={m['avg_win_loss_ratio']:.2f}  win%={m['win_rate']:.1f}")
        by_leg = {}
        for t in trades:
            by_leg.setdefault(t.leg, []).append(t)
        for leg, ts in by_leg.items():
            pnl = np.array([t.pnl for t in ts])
            gw = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
            print(f"    {leg}: n={len(ts)}  pnl=${pnl.sum():,.0f}  "
                  f"PF={gw/gl if gl>0 else float('inf'):.2f}  "
                  f"win%={len(pnl[pnl>0])/len(pnl)*100:.1f}")

    comb = all_trades["3_combined_shared"]
    ov = overlap_stats(comb)
    print(f"\n=== trade overlap (combined) ===")
    print(f"  overlapping H1/H4 pairs : {ov.get('overlapping_pairs',0)}")
    print(f"  same direction          : {ov.get('same_direction',0)} "
          f"({ov.get('same_dir_share_pct',0):.1f}% of overlaps)")
    print(f"  opposite direction      : {ov.get('opposite_direction',0)}")

    sweep = budget_sweep(h1, {"H1": plan_h1, "H4": plan_h4}, p)
    segs = oos_segments(h1, {"h1_only": {"H1": plan_h1},
                             "h4_only": {"H4": plan_h4},
                             "combined": {"H1": plan_h1, "H4": plan_h4}}, p)

    out = pd.DataFrame([{k: v for k, v in r.items() if k != "exits"} for r in rows])
    out.to_csv(os.path.join(REPORT_DIR, "portfolio_variants.csv"), index=False)
    sweep.to_csv(os.path.join(REPORT_DIR, "portfolio_budget_sweep.csv"), index=False)
    segs.to_csv(os.path.join(REPORT_DIR, "portfolio_oos.csv"), index=False)
    pd.DataFrame([asdict(t) for t in comb]).to_csv(
        os.path.join(REPORT_DIR, "portfolio_combined_trades.csv"), index=False)
    print(f"\nsaved CSVs to {REPORT_DIR}/")

    # Long-history cross-check: daily + weekly over 26 years, several regimes.
    run_tf("daily", "7D", folds=6)
    return 0


if __name__ == "__main__":
    sys.exit(main())
