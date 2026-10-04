#!/usr/bin/env python3
"""
Scan the MQL5 Signals service and score signals on risk, not headline growth.

Why this exists: MQL5's displayed rating and "Growth %" are gameable. Growth is
computed in a way that is distorted by deposits/withdrawals, and ratings come
from a handful of votes. This script pulls each signal's published equity curve
and computes drawdown and CAGR directly, so the numbers can be compared honestly.

Public data only. No authentication, no circumvention.

Usage:
    python3 research/signals_scan.py                 # top signals, gold-focused
    python3 research/signals_scan.py --pages 3       # scan more listing pages
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from curl_cffi import requests

BASE = "https://www.mql5.com"
LIST = BASE + "/en/signals/mt5"
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
GOLD_HINTS = ("gold", "xau")


def _get(session, url, **kw):
    for attempt in range(3):
        try:
            return session.get(url, timeout=40, **kw)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def parse_cards(html: str) -> list[dict]:
    out = []
    for c in re.split(r'<div class="signal-card">', html)[1:]:
        def g(pat, d=""):
            m = re.search(pat, c, re.S)
            return strip_tags(m.group(1)) if m else d
        sid = g(r'href="/en/signals/(\d+)"')
        if not sid:
            continue
        out.append({
            "id": sid,
            "name": g(r'data-name="([^"]+)"') or g(r'signal-card__title[^>]*>\s*<[^>]*>([^<]+)'),
            "author": g(r'signal-card__author__item">([^<]+)<'),
            "rating": g(r'g-rating__info">([^<]+)<'),
            "subscribers": g(r'signal-card__subscribers-value">([^<]+)<', "0"),
            "price": g(r'data-price="([^"]*)"'),
        })
    return out


def parse_signal(html: str) -> dict:
    d = {}
    for m in re.finditer(
        r's-list-info__label">([^<]+):\s*</div>\s*<div class="s-list-info__value">([^<]*)</div>', html
    ):
        d[strip_tags(m.group(1))] = strip_tags(m.group(2))
    for m in re.finditer(
        r's-data-columns__label">([^<]+):</div>\s*<div class="s-data-columns__value">(.*?)</div>', html, re.S
    ):
        d[strip_tags(m.group(1))] = strip_tags(m.group(2))
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        d["title"] = strip_tags(m.group(1))
    return d


def equity_curve(html: str):
    m = re.search(r"var equityData=\[(.*?)\];", html, re.S)
    if not m:
        return []
    nums = [float(x) for x in m.group(1).split(",") if x.strip()]
    return [(nums[i], nums[i + 1], nums[i + 2]) for i in range(0, len(nums) - 2, 3)]


def max_drawdown(values: list[float]) -> float:
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst * 100


def cagr(bal: list[float], ts: list[float]) -> float:
    years = (ts[-1] - ts[0]) / (365.25 * 24 * 3600)
    if years <= 0 or bal[0] <= 0 or bal[-1] <= 0:
        return 0.0
    return ((bal[-1] / bal[0]) ** (1 / years) - 1) * 100


def to_float(s):
    try:
        return float(re.sub(r"[^0-9.\-]", "", s.split("(")[0]) or 0)
    except ValueError:
        return 0.0


def pct_in_parens(s):
    """'638 (72.33%)' -> 72.33 ; returns 0 if absent."""
    m = re.search(r"\(([\d.]+)%\)", s)
    return float(m.group(1)) if m else 0.0


def score(row: dict) -> str:
    """Flag the pattern that makes a signal uncopyable in practice."""
    flags = []
    if row["max_dd"] > 40:
        flags.append("HIGH-DD")
    if row["win_rate"] > 90 and row["max_dd"] > 20:
        flags.append("MARTINGALE?")
    if row["consec_losses"] >= 15:
        flags.append("LONG-LOSS-STREAK")
    if row["deposit_load"] > 20:
        flags.append("HEAVY-LEVERAGE")
    if row["weeks"] < 52:
        flags.append("<1YEAR")
    return ",".join(flags) if flags else "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--all", action="store_true", help="scan every signal, not just gold")
    args = ap.parse_args()

    session = requests.Session(impersonate="chrome")
    seen = {}
    for page in range(1, args.pages + 1):
        url = LIST if page == 1 else f"{LIST}/page{page}"
        r = _get(session, url)
        if r.status_code != 200:
            print(f"listing page {page}: HTTP {r.status_code}")
            continue
        for c in parse_cards(r.text):
            seen[c["id"]] = c
    print(f"found {len(seen)} unique signals\n")

    rows = []
    for sid, card in seen.items():
        if not args.all and not any(h in card["name"].lower() for h in GOLD_HINTS):
            continue
        try:
            r = _get(session, f"{BASE}/en/signals/{sid}")
        except Exception as e:
            print(f"{sid} {card['name']}: fetch failed ({e})")
            continue
        if r.status_code != 200:
            continue
        d = parse_signal(r.text)
        pts = equity_curve(r.text)
        if not pts:
            continue
        ts = [p[0] for p in pts]
        bal = [p[1] for p in pts]
        rows.append({
            "id": sid,
            "name": card["name"],
            "price": card["price"],
            "subs": card["subscribers"],
            "weeks": int(to_float(d.get("Weeks", "0"))),
            "trades": int(to_float(d.get("Trades", "0"))),
            "win_rate": pct_in_parens(d.get("Profit Trades", "0")),
            "growth_hdr": to_float(d.get("Growth", "0")),
            "balance": to_float(d.get("Balance", "0")),
            "max_dd": round(max_drawdown(bal), 1),
            "cagr": round(cagr(bal, ts), 1),
            "consec_losses": int(to_float(d.get("Maximum consecutive losses", "0"))),
            "deposit_load": to_float(d.get("Max deposit load", "0")),
            "sharpe": to_float(d.get("Sharpe Ratio", "0")),
            "expectancy": to_float(d.get("Expected Payoff", "0")),
        })
        time.sleep(0.6)

    if not rows:
        print("no signals parsed")
        return 1

    rows.sort(key=lambda x: x["cagr"] / max(x["max_dd"], 1), reverse=True)
    for r in rows:
        r["flag"] = score(r)

    print(f"{'signal':32s} {'weeks':>5s} {'trades':>6s} {'win%':>6s} {'hdr growth':>10s} "
          f"{'maxDD':>6s} {'CAGR':>7s} {'Sharpe':>6s} {'flag'}")
    print("-" * 118)
    for r in rows:
        print(f"{r['name'][:32]:32s} {r['weeks']:5d} {r['trades']:6d} {r['win_rate']:6.1f} "
              f"{r['growth_hdr']:10.0f} {r['max_dd']:6.1f} {r['cagr']:7.1f} {r['sharpe']:6.2f} {r['flag']}")

    os.makedirs(REPORT_DIR, exist_ok=True)
    import csv
    path = os.path.join(REPORT_DIR, "signals_scan.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nsaved {len(rows)} signals -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
