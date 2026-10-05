#!/usr/bin/env python3
"""
Fetch XAUUSD H1 candles from the Deriv API and emit a broker-style CSV.

Why this exists: the free cache is a COMEX futures proxy, and the long-history
research gate needs 8+ years of the ACTUAL traded instrument. Deriv's
`ticks_history` is no-auth for market data and returns true-UTC epochs, so it is
a better source than an MT5 CSV export (no broker-server-time guesswork).

This module is deliberately split so the network layer is thin and the paging /
dedup / conversion logic is testable without a network:

  DerivClient          - the only part that touches the socket
  fetch_candles(...)   - pages backwards using an injected client
  candles_to_frame(...)- epoch -> tz-naive UTC harness frame
  write_broker_csv(...)- harness frame -> Date,Time,OHLC CSV

Credentials: public market data needs NO api token. `--app-id` (or the
DERIV_APP_ID env var) only identifies the application and defaults to the public
1089. Never pass an API *token* here - it is not needed and would be a leak.

Usage:
    python3 research/deriv_fetch.py --list
    python3 research/deriv_fetch.py --probe  --symbol frxXAUUSD
    python3 research/deriv_fetch.py --fetch  --symbol frxXAUUSD \
        --out research/data/deriv_XAUUSD_H1_raw.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_APP_ID = "1089"           # public app id; fine for no-auth market data
DEFAULT_WS = "wss://ws.derivws.com/websockets/v3"
GRANULARITY = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600,
               "H4": 14400, "D1": 86400}
MAX_COUNT = 5000                  # request cap per call


@dataclass
class DerivClient:
    """Thin wrapper over the Deriv websocket. The only networked part."""
    app_id: str = DEFAULT_APP_ID
    url: str = DEFAULT_WS
    timeout: int = 30

    def __post_init__(self):
        import websocket   # imported lazily so the module loads without it
        self._ws = websocket.create_connection(
            f"{self.url}?app_id={self.app_id}", timeout=self.timeout,
            origin="https://app.deriv.com")
        self._ws.settimeout(self.timeout)

    def call(self, req: dict, expect: str, retries: int = 4) -> dict:
        last = None
        for attempt in range(retries):
            self._ws.send(json.dumps(req))
            for _ in range(20):
                msg = json.loads(self._ws.recv())
                if "error" in msg:
                    last = msg["error"]
                    break
                if msg.get("msg_type") == expect:
                    return msg
            time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"request failed: {last}")

    def close(self):
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001
            pass


def list_gold_symbols(client: DerivClient) -> list[tuple[str, str]]:
    r = client.call({"active_symbols": "brief", "product_type": "basic"},
                    "active_symbols")
    out = []
    for s in r.get("active_symbols", []):
        name = (s.get("display_name") or "")
        if "XAU" in s.get("symbol", "") or "Gold" in name:
            out.append((s["symbol"], name))
    return out


def _one_page(client: DerivClient, symbol: str, granularity: int, end_epoch: int,
              count: int) -> list[dict]:
    req = {"ticks_history": symbol, "adjust_start_time": 1, "count": count,
           "end": int(end_epoch), "style": "candles", "granularity": granularity}
    try:
        r = client.call(req, "candles")
    except RuntimeError:
        if count > 500:      # some accounts cap count lower; retry smaller
            return _one_page(client, symbol, granularity, end_epoch, 500)
        raise
    return r.get("candles") or []


def fetch_candles(client, symbol: str, granularity: int, start_epoch: int | None = None,
                  max_pages: int = 200, count: int = MAX_COUNT, sleep_s: float = 0.25,
                  progress: bool = True) -> list[dict]:
    """Page backwards from `end` (now) until the start of history or start_epoch.

    Candles are deduplicated by epoch and returned ascending. Stops when a page
    returns fewer than requested (history exhausted) or the cap is hit.
    """
    end = int(time.time())
    collected: dict[int, dict] = {}
    for page in range(max_pages):
        batch = _one_page(client, symbol, granularity, end, count)
        if not batch:
            break
        for c in batch:
            collected[int(c["epoch"])] = c
        oldest = min(int(c["epoch"]) for c in batch)
        if progress:
            print(f"  page {page+1:3d}: {len(batch):5d} candles, "
                  f"oldest {time.strftime('%Y-%m-%d %H:%M', time.gmtime(oldest))}, "
                  f"total {len(collected)}", flush=True)
        if len(batch) < count:
            break                      # reached the beginning of history
        if start_epoch is not None and oldest <= int(start_epoch):
            break
        end = oldest - granularity     # step strictly before the oldest we have
        time.sleep(sleep_s)
    return [collected[k] for k in sorted(collected)]


def candles_to_frame(candles: list[dict]) -> pd.DataFrame:
    """Epoch candles -> tz-naive UTC harness frame (matches the loader's convention)."""
    if not candles:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    df = pd.DataFrame({
        "Open": [float(c["open"]) for c in candles],
        "High": [float(c["high"]) for c in candles],
        "Low": [float(c["low"]) for c in candles],
        "Close": [float(c["close"]) for c in candles],
    })
    df.index = pd.to_datetime([int(c["epoch"]) for c in candles], unit="s", utc=True)\
                 .tz_localize(None)
    df.index.name = "datetime"
    return df


def write_broker_csv(df: pd.DataFrame, path: str):
    out = pd.DataFrame({
        "Date": df.index.strftime("%Y.%m.%d"),
        "Time": df.index.strftime("%H:%M:%S"),
        "Open": df["Open"].to_numpy(),
        "High": df["High"].to_numpy(),
        "Low": df["Low"].to_numpy(),
        "Close": df["Close"].to_numpy(),
    })
    out.to_csv(path, index=False)


def _looks_like_token(s: str) -> bool:
    """Deriv API tokens are 15 lowercase alphanumerics; app ids are 20 mixed."""
    return len(s) <= 15 and s.islower() and s.isalnum()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-id", default=os.environ.get("DERIV_APP_ID", DEFAULT_APP_ID),
                    help="Deriv app id (NOT an API token); public default is 1089")
    ap.add_argument("--url", default=DEFAULT_WS)
    ap.add_argument("--symbol", default="frxXAUUSD")
    ap.add_argument("--granularity", default="H1", choices=list(GRANULARITY))
    ap.add_argument("--out", help="output CSV path (for --fetch)")
    ap.add_argument("--start", type=int, help="stop paging at/below this epoch")
    ap.add_argument("--max-pages", type=int, default=200)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list gold symbols")
    g.add_argument("--probe", action="store_true",
                   help="find the OLDEST available candle (the decision point)")
    g.add_argument("--fetch", action="store_true", help="download candles to CSV")
    args = ap.parse_args()

    if _looks_like_token(args.app_id):
        print("WARNING: --app-id looks like an API TOKEN (15 lowercase chars).")
        print("         Market data needs no token. If this is a token, do not use it")
        print("         here and rotate it - it was not needed.")

    try:
        client = DerivClient(app_id=args.app_id, url=args.url)
    except Exception as e:  # noqa: BLE001
        print(f"CONNECT FAILED: {type(e).__name__}: {e}")
        print("This host must be reachable from where you run it. A Cloudflare 520")
        print("here means network egress is blocked, not a credential problem.")
        return 1

    try:
        if args.list:
            for sym, name in list_gold_symbols(client):
                print(f"  {sym:16s} {name}")
            return 0

        gran = GRANULARITY[args.granularity]
        print(f"symbol={args.symbol} granularity={args.granularity} ({gran}s)")

        if args.probe:
            print("paging backwards to find the earliest available candle...")
            cs = fetch_candles(client, args.symbol, gran, start_epoch=args.start,
                               max_pages=args.max_pages)
            if not cs:
                print("no candles returned - check the symbol name (--list)")
                return 1
            first = cs[0]["epoch"]
            last = cs[-1]["epoch"]
            years = (last - first) / (365.25 * 86400)
            print(f"\nEARLIEST available : {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(first))}")
            print(f"LATEST   available : {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last))}")
            print(f"total candles      : {len(cs)}   span: {years:.1f} years")
            print(f"\nVERDICT: {'REACHES the 8-year gate' if years >= 8 else 'TOO SHORT for the 8-year gate'}")
            return 0 if years >= 8 else 1

        if args.fetch:
            if not args.out:
                print("--fetch requires --out PATH")
                return 1
            cs = fetch_candles(client, args.symbol, gran, start_epoch=args.start,
                               max_pages=args.max_pages)
            df = candles_to_frame(cs)
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            write_broker_csv(df, args.out)
            print(f"\nwrote {len(df)} candles to {args.out}")
            print(f"  {df.index.min()} .. {df.index.max()} (tz-naive UTC)")
            print("\nnext:")
            print(f"  python3 research/preflight.py --csv {args.out}")
            print(f"  python3 research/validate_import.py --csv {args.out}")
            print(f"  python3 research/compare_instruments.py --csv {args.out}")
            print(f"  python3 research/long_history.py --csv {args.out} --folds 8")
            return 0
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
