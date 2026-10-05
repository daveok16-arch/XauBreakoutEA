#!/usr/bin/env python3
"""
H4 strategy leg for the multi-timeframe study.

The H4 leg is deliberately built to avoid look-ahead:

  - H4 candles are resampled from H1 and labelled by their CLOSE time.
  - A signal on H4 bar j uses only bars up to and including j, and the breakout
    level uses bars up to j-1 (shift(1)). Both are complete at the label time.
  - The entry is placed at the OPEN of the first H1 bar at or after the H4
    close time. This is the earliest realistic fill: you cannot trade an H4
    breakout before the H4 candle has closed, and the next tradeable price is
    the following H1 open.
  - The same spread / commission assumptions as the rest of the harness apply.

The leg exposes `entry_plan(h1, h4, p)` -> {h1_bar_index: (side, atr, stop_dist)}
so the portfolio engine can interleave H4 entries with H1 entries on a single
timeline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy import Params, atr_wilder


def resample_tf(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate to a higher timeframe, labelled by close time (no look-ahead)."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(rule, label="right", closed="right").agg(agg).dropna()


def resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate H1 into 4-hour bars, labelled by close time (no look-ahead)."""
    return resample_tf(h1, "4h")


def h4_signals(h4: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Breakout level (prior bars only) and ATR, evaluated on completed H4 bars."""
    atr = atr_wilder(h4, p.atr_period)
    hh = h4["High"].rolling(p.lookback).max().shift(1)
    ll = h4["Low"].rolling(p.lookback).min().shift(1)
    return pd.DataFrame({"hh": hh, "ll": ll, "atr": atr, "close": h4["Close"]})


def entry_plan(h1: pd.DataFrame, h4: pd.DataFrame, p: Params) -> dict:
    """Map higher-timeframe breakout signals onto lower-timeframe entry bars.

    Returns {base_index: (side, atr, stop_dist)}. The base_index is the first
    base bar opening at or after the HTF bar's close, so the fill is realistic.
    Works for H4-from-H1 or W1-from-daily.
    """
    sig = h4_signals(h4, p)
    h1_pos = np.searchsorted(h1.index.values, h4.index.values, side="left")
    plan: dict[int, tuple] = {}
    n = len(h1)
    for j in range(len(sig)):
        if h1_pos[j] >= n:
            break
        row = sig.iloc[j]
        if np.isnan(row["hh"]) or np.isnan(row["atr"]) or row["atr"] <= 0:
            continue
        long_sig = row["close"] > row["hh"]
        short_sig = row["close"] < row["ll"]
        if not (long_sig or short_sig):
            continue
        i = int(h1_pos[j])
        if i in plan:            # two H4 bars can share an H1 open after a gap
            continue
        side = "long" if long_sig else "short"
        plan[i] = (side, float(row["atr"]), p.stop_atr * float(row["atr"]))
    return plan


def h1_entry_plan(h1: pd.DataFrame, p: Params) -> dict:
    """H1 breakout signals, evaluated on completed H1 bars (mirrors strategy.py)."""
    atr = atr_wilder(h1, p.atr_period).to_numpy()
    hh = h1["High"].rolling(p.lookback).max().shift(1).to_numpy()
    ll = h1["Low"].rolling(p.lookback).min().shift(1).to_numpy()
    close = h1["Close"].to_numpy()
    plan: dict[int, tuple] = {}
    for i in range(1, len(h1)):
        if np.isnan(atr[i - 1]) or np.isnan(hh[i - 1]):
            continue
        long_sig = close[i - 1] > hh[i - 1]
        short_sig = close[i - 1] < ll[i - 1]
        if not (long_sig or short_sig):
            continue
        side = "long" if long_sig else "short"
        plan[i] = (side, float(atr[i - 1]), p.stop_atr * float(atr[i - 1]))
    return plan
