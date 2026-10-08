#!/usr/bin/env python3
"""
Head-to-head: our EA vs Gold Reaper, on the same basis.

Both are reduced to per-trade R multiples so they can be compared despite running
different instruments/timeframes. For Gold Reaper we only have the public balance
curve (each step = one closed trade), so R is normalised by its own average loss.
For our EA the trades carry true R (risk was fixed per trade).

What this can and cannot say:
  - CAN compare edge SHAPE: win rate, avg win/loss, expectancy, PF, drawdown.
  - CAN fingerprint sizing: does loss size grow with drawdown depth (recovery) or
    track equity (compounding)?
  - CANNOT compare CAGR fairly: different period, instrument and account. A raw
    return number would be apples-to-oranges.

Usage:
    python3 research/compare_reaper.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

import gold_reaper_analysis as gra
import fetch_data
import strategy
from dataclasses import replace

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def _stats_from_pnl(pnl: np.ndarray, bal: np.ndarray | None) -> dict:
    """Metrics from a sequence of per-trade P&L (in account currency)."""
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    # normalise to R: 1R = average loss
    R = abs(avg_loss) if avg_loss else 1.0
    r_mult = pnl / R

    out = {
        "trades": len(pnl),
        "win_pct": len(wins) / len(pnl) * 100 if len(pnl) else 0.0,
        "avg_win_R": avg_win / R if R else 0.0,
        "avg_loss_R": avg_loss / R if R else 0.0,
        "wl_ratio": abs(avg_win / avg_loss) if avg_loss else float("inf"),
        "pf": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_R": r_mult.mean() if len(pnl) else 0.0,
        "max_consec_loss": _longest_run(pnl < 0),
    }
    if bal is not None and len(bal):
        peak = np.maximum.accumulate(bal)
        dd = (peak - bal) / peak * 100
        out["max_dd_pct"] = dd.max()
        # sizing-neutral expectancy: mean per-trade return as % of balance.
        # Removes the compounding/sizing growth so the two are comparable.
        pct = pnl / bal * 100
        out["pct_per_trade"] = pct.mean()
        # consistency: same sign in both halves of the record?
        h = len(pct) // 2
        out["half1_pct"] = pct[:h].mean() if h else float("nan")
        out["half2_pct"] = pct[h:].mean() if h else float("nan")
        # recovery fingerprint: loss size (as % of balance) vs drawdown depth
        m = pct < 0
        if m.sum() > 30:
            out["recovery_corr"] = np.corrcoef(dd[m], np.abs(pct[m]))[0, 1]
        else:
            out["recovery_corr"] = float("nan")
    return out


def _longest_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def gold_reaper() -> dict:
    html = gra.fetch(gra.URL)
    pts = gra.equity_curve(html)
    steps = gra.balance_steps(pts)
    pnl = np.array([s[1] for s in steps])
    bal = np.array([s[2] for s in steps])
    st = _stats_from_pnl(pnl, bal)
    st["name"] = "Gold Reaper V2 (signal 2265877)"
    st["note"] = "public balance curve; R = avg loss"
    return st


def ours(tf: str) -> dict:
    df = fetch_data.load(tf)
    p = replace(strategy.Params(), allow_short=False)   # the proven long-only side
    curve, trades, max_dd = strategy.backtest(df, p)
    m = strategy.metrics(curve, trades, max_dd, p)
    r = np.array([t.r_multiple for t in trades])
    st = {
        "name": f"our EA long-only [{tf}]",
        "note": "true R (fixed risk per trade)",
        "trades": len(r),
        "win_pct": (r > 0).mean() * 100,
        "avg_win_R": r[r > 0].mean() if (r > 0).any() else 0.0,
        "avg_loss_R": r[r < 0].mean() if (r < 0).any() else 0.0,
        "wl_ratio": abs(r[r > 0].mean() / r[r < 0].mean()) if (r < 0).any() else float("inf"),
        "pf": m["profit_factor"],
        "expectancy_R": r.mean(),
        "max_consec_loss": m["max_consec_losses"],
        "max_dd_pct": m["max_dd_pct"],
        "recovery_corr": 0.0,   # fixed-fraction sizing: size does not track losses
    }
    return st


def print_row(label: str, a: dict, b: dict, fmt: str, key: str):
    va, vb = a.get(key), b.get(key)
    def f(v):
        if v is None:
            return "  n/a"
        if isinstance(v, float) and not np.isfinite(v):
            return "  inf"
        return format(v, fmt)
    print(f"  {label:26s} {f(va):>12s} {f(vb):>14s}")


def main() -> int:
    gr = gold_reaper()
    ours_d = ours("daily")
    ours_h1 = ours("h1")

    print("=" * 78)
    print("GOLD REAPER vs OUR EA  (reduced to per-trade R for comparability)")
    print("=" * 78)
    for col, data in [("Gold Reaper", gr), ("ours daily", ours_d), ("ours H1", ours_h1)]:
        print(f"\n{col}: {data['name']}")
        print(f"  {data['note']}")
    print("\n" + "-" * 78)
    hdr = f"  {'metric':26s} {'Gold Reaper':>12s} {'ours daily':>14s}"
    print(hdr)
    print("  " + "-" * 74)
    print_row("trades", gr, ours_d, ".0f", "trades")
    print_row("win rate %", gr, ours_d, ".1f", "win_pct")
    print_row("avg win (R)", gr, ours_d, "+.2f", "avg_win_R")
    print_row("avg loss (R)", gr, ours_d, "+.2f", "avg_loss_R")
    print_row("win/loss ratio", gr, ours_d, ".2f", "wl_ratio")
    print_row("profit factor", gr, ours_d, ".2f", "pf")
    print_row("expectancy (R/trade)", gr, ours_d, "+.3f", "expectancy_R")
    print_row("max consec losses", gr, ours_d, ".0f", "max_consec_loss")
    print_row("max drawdown %", gr, ours_d, ".1f", "max_dd_pct")
    print_row("recovery corr", gr, ours_d, "+.3f", "recovery_corr")
    print("\n  sizing-neutral (per-trade % of balance):")
    print_row("mean % / trade", gr, {"pct_per_trade": ours_d["expectancy_R"] * 0.75}, "+.3f", "pct_per_trade")
    print_row("  Gold Reaper 1st half %", gr, {}, "+.3f", "half1_pct")
    print_row("  Gold Reaper 2nd half %", gr, {}, "+.3f", "half2_pct")

    print("\n" + "-" * 78)
    print("READING IT")
    print("-" * 78)
    print(f"  Gold Reaper: wins {gr['win_pct']:.0f}% of trades but its avg win is")
    print(f"    {gr['wl_ratio']:.1f}x its avg loss - a low-win, big-win shape.")
    print(f"    expectancy {gr['expectancy_R']:+.3f}R per trade, PF {gr['pf']:.2f}.")
    rc = gr.get("recovery_corr", float("nan"))
    if np.isfinite(rc):
        verdict = ("weak/absent" if rc < 0.15 else
                   "moderate - loss size does grow with drawdown" if rc < 0.4 else
                   "strong - recovery/martingale signature")
        print(f"    recovery corr {rc:+.3f} -> {verdict}.")
    print(f"  ours: wins {ours_d['win_pct']:.0f}%, avg win {ours_d['wl_ratio']:.1f}x avg loss,")
    print(f"    expectancy {ours_d['expectancy_R']:+.3f}R per trade, PF {ours_d['pf']:.2f},")
    print(f"    fixed-fraction sizing so recovery corr is 0 by construction.")
    print("\n  Different instruments/periods, so CAGR is NOT comparable here - only")
    print("  the edge shape and the sizing fingerprint are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
