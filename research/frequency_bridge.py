#!/usr/bin/env python3
"""
Frequency bridge: can we raise trade COUNT on the PROVEN long-only edge without
destroying it?

The lesson of the $12 question was that our edge is real but slow: ~7.5 trades/yr
means a tiny account compounds over centuries. So the honest route to the
small-account goal is not a new unproven scalp - it is to make the edge we have
already proven fire more often. This tool measures the trade-off.

We test three levers, each keeping the proven ingredients (long-only, Donchian
breakout, ATR-buffered stop, close-confirmed):

  1. lookback  - a shorter Donchian N fires more often; how much edge survives?
  2. timeframe - H1 bars give many more breakout opportunities than daily
  3. channels  - run several lookbacks at once (each with its own stop distance)
                 and share one risk budget

The number to watch is ANNUALISED EV: trades/yr x expectancy(R) x risk%/trade.
A shorter lookback can lower per-trade edge yet still raise annual EV if the
trade count rises more than the edge falls. That is the only trade-off that
matters here.

Usage:
    python3 research/frequency_bridge.py
    python3 research/frequency_bridge.py --tf h1
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import numpy as np

import fetch_data
import strategy
from ev_decomposition import _t_stat, _chunk_consistency


def run(df, p, label):
    curve, trades, dd = strategy.backtest(df, p)
    m = strategy.metrics(curve, trades, dd, p)
    r = np.array([t.r_multiple for t in trades])
    years = (df.index[-1] - df.index[0]).days / 365.25
    tpy = len(trades) / years if years > 0 else 0.0
    ann_ev = tpy * r.mean() * (p.risk_pct / 100.0) * 100 if len(r) else 0.0
    t = _t_stat(r) if len(r) >= 2 else 0.0
    pos, tot = _chunk_consistency(r, [t.entry_time for t in trades]) if len(r) else (0, 0)
    return {
        "label": label, "n": len(r), "tpy": tpy, "win": (r > 0).mean() * 100 if len(r) else 0,
        "avgR": r.mean() if len(r) else 0.0, "pf": m["profit_factor"],
        "dd": m["max_dd_pct"], "cagr": m["cagr_pct"], "t": t, "chunks": f"{pos}/{tot}",
        "ann_ev": ann_ev,
    }


def print_table(rows, title, note=""):
    print(f"\n=== {title} ===")
    if note:
        print(f"  {note}")
    hdr = (f"  {'variant':>18s} {'n':>5s} {'trades/yr':>9s} {'win%':>5s} {'avgR':>7s} "
           f"{'PF':>5s} {'maxDD%':>7s} {'t':>6s} {'chunks':>7s} {'annEV%':>7s}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for x in rows:
        print(f"  {x['label']:>18s} {x['n']:5d} {x['tpy']:9.1f} {x['win']:5.1f} {x['avgR']:+7.3f} "
              f"{x['pf']:5.2f} {x['dd']:7.1f} {x['t']:6.2f} {x['chunks']:>7s} {x['ann_ev']:7.1f}")


def lookback_sweep(df, tf):
    base = replace(strategy.Params(), allow_short=False)
    rows = []
    for n in (5, 10, 20, 40, 60, 120):
        rows.append(run(df, replace(base, lookback=n), f"N={n}"))
    print_table(rows, f"lookback sweep [{tf}]", "shorter N = more trades; watch annEV, not avgR")


def channel_sweep(df, tf, lookbacks=(10, 20, 60)):
    """Several lookbacks run independently; per-trade EV is the weighted mean,
    and annual EV is the sum of the channels' annual EVs (independent signals on
    the same account). Shows the diversification-free frequency gain."""
    base = replace(strategy.Params(), allow_short=False)
    rows = []
    for n in lookbacks:
        rows.append(run(df, replace(base, lookback=n), f"single N={n}"))
    # combined: pool all trades from the channels
    all_r, all_t, total_ann = [], [], 0.0
    for n in lookbacks:
        _, trades, _ = strategy.backtest(df, replace(base, lookback=n))
        r = np.array([t.r_multiple for t in trades])
        all_r.append(r)
        all_t += [t.entry_time for t in trades]
        total_ann += rows[lookbacks.index(n)]["ann_ev"]
    r = np.concatenate(all_r)
    t = _t_stat(r)
    pos, tot = _chunk_consistency(r, all_t)
    rows.append({
        "label": "combined", "n": len(r), "tpy": sum(x["tpy"] for x in rows),
        "win": (r > 0).mean() * 100, "avgR": r.mean(),
        "pf": float("nan"), "dd": float("nan"), "cagr": float("nan"),
        "t": t, "chunks": f"{pos}/{tot}", "ann_ev": total_ann,
    })
    print_table(rows, f"channel combination [{tf}]",
                "combined pools the channels; annEV sums them (shared budget not modelled here)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1"])
    args = ap.parse_args()
    df = fetch_data.load(args.tf)
    print(f"data: {len(df)} {args.tf} bars  {df.index[0].date()}..{df.index[-1].date()}")
    lookback_sweep(df, args.tf)
    channel_sweep(df, args.tf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
