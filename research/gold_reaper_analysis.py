#!/usr/bin/env python3
"""
Reverse-engineer the risk/position-sizing behaviour of a MQL5 signal from its
published balance curve.

Full per-trade history requires an MQL5 login, so this works from the public
`equityData` curve. Each step in the balance curve is a closed trade, so the
sequence of balance changes is a usable proxy for the trade P&L sequence. That
is enough to fingerprint the sizing *style* (fixed-risk vs recovery/martingale)
even though individual lot sizes are not published.

Usage:
    python3 research/gold_reaper_analysis.py
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from curl_cffi import requests

SIGNAL_ID = 2265877  # Gold Reaper New V2 2
URL = f"https://www.mql5.com/en/signals/{SIGNAL_ID}"
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def fetch(url):
    r = requests.get(url, impersonate="chrome", timeout=40)
    r.raise_for_status()
    return r.text


def equity_curve(html):
    m = re.search(r"var equityData=\[(.*?)\];", html, re.S)
    nums = [float(x) for x in m.group(1).split(",") if x.strip()]
    return [(nums[i], nums[i + 1], nums[i + 2]) for i in range(0, len(nums) - 2, 3)]


def balance_steps(pts):
    """Collapse the time-sampled balance curve into distinct balance changes."""
    steps = []
    prev = pts[0][1]
    for ts, bal, _eq in pts[1:]:
        if abs(bal - prev) > 1e-9:
            steps.append((ts, bal - prev, bal))
            prev = bal
    return steps


def main() -> int:
    html = fetch(URL)
    pts = equity_curve(html)
    steps = balance_steps(pts)
    pnl = np.array([s[1] for s in steps])
    bal = np.array([s[2] for s in steps])
    ts = np.array([s[0] for s in steps])

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    print(f"Gold Reaper V2  (signal {SIGNAL_ID})")
    print(f"  curve points        : {len(pts)}")
    print(f"  reconstructed steps : {len(steps)}")
    print(f"  wins / losses       : {len(wins)} / {len(losses)}")
    print(f"  avg win / avg loss  : {wins.mean():.2f} / {losses.mean():.2f}")
    print(f"  win/loss ratio      : {abs(wins.mean()/losses.mean()):.2f}")
    print(f"  largest win / loss  : {wins.max():.2f} / {losses.min():.2f}")
    print(f"  std of losses       : {losses.std():.2f}")

    # Martingale fingerprint: does the size of a loss grow with the depth of the
    # drawdown it occurs in? Fixed-risk sizing -> flat; recovery sizing -> rising.
    peak = np.maximum.accumulate(bal)
    dd = (peak - bal) / peak * 100
    loss_dd = dd[pnl < 0]
    loss_amt = np.abs(pnl[pnl < 0])
    if len(loss_amt) > 30:
        corr = np.corrcoef(loss_dd, loss_amt)[0, 1]
        print(f"  corr(drawdown depth, loss size) : {corr:+.3f}")

    # Runs: are losses isolated (fixed risk) or clustered after wins (recovery)?
    print(f"  longest loss run    : {_longest_run(pnl < 0)}")
    print(f"  longest win run     : {_longest_run(pnl > 0)}")

    # Bucketed loss size across the life of the signal: growth in lot sizing?
    # Raw $ losses grow with the account, so normalise by balance at the time.
    pct = pnl / bal * 100.0
    q = np.array_split(np.abs(pct[pct < 0]), 4)
    print("  mean loss % of bal by quartile: " + "  ".join(f"{b.mean():5.2f}" for b in q if len(b)))
    qw = np.array_split(pct[pct > 0], 4)
    print("  mean win  % of bal by quartile: " + "  ".join(f"{b.mean():5.2f}" for b in qw if len(b)))

    # Recovery-sizing fingerprint, account-growth removed: does % risk rise with
    # drawdown depth? Fixed-fractional -> flat; martingale/recovery -> rising.
    peak_pct = np.maximum.accumulate(bal)
    dd_pct = (peak_pct - bal) / peak_pct * 100
    m = pct < 0
    if m.sum() > 30:
        corr_n = np.corrcoef(dd_pct[m], np.abs(pct[m]))[0, 1]
        print(f"  corr(drawdown depth, loss as %bal): {corr_n:+.3f}")

    os.makedirs(REPORT_DIR, exist_ok=True)
    dates = [datetime.fromtimestamp(t, tz=timezone.utc) for t in ts]
    fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax[0].plot(dates, bal, lw=1.2, color="#1a7f37")
    ax[0].set_ylabel("Balance (USD)")
    ax[0].set_title("Gold Reaper V2 - published balance curve")
    ax[0].grid(alpha=0.3)
    ax[1].plot(dates, dd, lw=1.0, color="#c62828")
    ax[1].fill_between(dates, dd, 0, color="#c62828", alpha=0.15)
    ax[1].set_ylabel("Drawdown (%)")
    ax[1].grid(alpha=0.3)
    out = os.path.join(REPORT_DIR, "gold_reaper_curve.png")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(f"\nsaved chart -> {out}")
    return 0


def _longest_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


if __name__ == "__main__":
    sys.exit(main())
