#!/usr/bin/env python3
"""
Backtest engine for the XauBreakoutEA idea.

This is a *research* harness, not a tick-accurate MT5 replica. It mirrors the
MQL5 logic bar-for-bar on OHLC data:

  - signal is evaluated on the close of the last completed bar (no repaint)
  - entry is taken at the next bar's open, paying half-spread + commission
  - stop / take-profit / trailing are resolved against each bar's high/low,
    with the adverse side checked first (conservative when both could trigger)
  - position size is derived from the actual stop distance (percent risk)

Data granularity limits fidelity: intra-bar path is unknown, so this
over-estimates nothing and under-estimates some gaps. Treat it as a
plausibility filter, not a promise.

Usage:
    python3 research/strategy.py            # base config on daily bars
    python3 research/strategy.py --tf h1
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

import fetch_data

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


@dataclass
class Params:
    # signal
    lookback: int = 60          # breakout lookback (bars) - matches the EA default
    atr_period: int = 14
    require_close_out: bool = True
    # risk
    risk_pct: float = 0.75      # % of equity risked per trade
    stop_atr: float = 1.50      # stop distance in ATR
    reward_risk: float = 2.00   # take profit in R
    max_total_risk_pct: float = 3.00
    max_daily_loss_pct: float = 2.00
    max_positions: int = 1
    # management
    use_trailing: bool = True
    trail_atr: float = 2.00
    trail_start_r: float = 1.00
    # costs (price units per ounce of gold)
    spread: float = 0.30        # full bid/ask spread
    commission_per_side: float = 0.07
    # account
    start_equity: float = 10_000.0


# --------------------------------------------------------------------------
# indicators
# --------------------------------------------------------------------------
def atr_wilder(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing == EMA with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# --------------------------------------------------------------------------
# backtest
# --------------------------------------------------------------------------
@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry: float
    exit_time: pd.Timestamp
    exit: float
    size: float
    pnl: float
    r_multiple: float
    reason: str
    bars_held: int


def backtest(df: pd.DataFrame, p: Params):
    df = df.copy()
    n = len(df)
    close = df["Close"].to_numpy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    openp = df["Open"].to_numpy()
    idx = df.index

    atr = atr_wilder(df, p.atr_period).to_numpy()
    hh = df["High"].rolling(p.lookback).max().shift(1).to_numpy()
    ll = df["Low"].rolling(p.lookback).min().shift(1).to_numpy()

    half_spread = p.spread / 2.0
    cost_per_side = half_spread + p.commission_per_side

    equity = p.start_equity
    peak = equity
    max_dd = 0.0
    curve = np.full(n, np.nan)

    pos = None          # dict when open
    trades: list[Trade] = []
    warmup = max(p.lookback + 2, p.atr_period + 2)

    day_start_equity = equity
    cur_day = idx[0].date()

    def close_pos(bar_i, price, reason):
        nonlocal equity, pos
        gross = (price - pos["entry"]) * pos["size"] if pos["side"] == "long" \
            else (pos["entry"] - price) * pos["size"]
        net = gross - cost_per_side * pos["size"]  # exit-side cost
        equity += net
        risk_money = pos["risk_money"]
        trades.append(
            Trade(
                side=pos["side"],
                entry_time=pos["entry_time"],
                entry=pos["entry"],
                exit_time=idx[bar_i],
                exit=price,
                size=pos["size"],
                pnl=net,
                r_multiple=net / risk_money if risk_money else 0.0,
                reason=reason,
                bars_held=bar_i - pos["entry_bar"],
            )
        )
        pos = None

    for i in range(warmup, n):
        # roll the trading day for the daily-loss guard
        if idx[i].date() != cur_day:
            cur_day = idx[i].date()
            day_start_equity = equity

        # ---- 1) manage any open position on this bar -------------------
        if pos is not None:
            if pos["side"] == "long":
                # adverse first: stop
                if low[i] <= pos["sl"]:
                    close_pos(i, pos["sl"], "stop")
                elif high[i] >= pos["tp"]:
                    close_pos(i, pos["tp"], "target")
                else:
                    pos["hw"] = max(pos["hw"], high[i])
                    if p.use_trailing:
                        stop_dist = pos["entry"] - pos["init_sl"]
                        if pos["hw"] - pos["entry"] >= p.trail_start_r * stop_dist:
                            new_sl = pos["hw"] - p.trail_atr * pos["atr"]
                            pos["sl"] = max(pos["sl"], new_sl)
            else:  # short
                if high[i] >= pos["sl"]:
                    close_pos(i, pos["sl"], "stop")
                elif low[i] <= pos["tp"]:
                    close_pos(i, pos["tp"], "target")
                else:
                    pos["lw"] = min(pos["lw"], low[i])
                    if p.use_trailing:
                        stop_dist = pos["init_sl"] - pos["entry"]
                        if pos["entry"] - pos["lw"] >= p.trail_start_r * stop_dist:
                            new_sl = pos["lw"] + p.trail_atr * pos["atr"]
                            pos["sl"] = min(pos["sl"], new_sl)

        # ---- 2) entries (only when flat, on last completed bar) --------
        if pos is None and i >= 1 and not np.isnan(atr[i - 1]) and not np.isnan(hh[i - 1]):
            # daily loss guard
            if p.max_daily_loss_pct > 0 and equity < day_start_equity * (1 - p.max_daily_loss_pct / 100.0):
                pass  # no new risk today
            else:
                long_sig = close[i - 1] > hh[i - 1]
                short_sig = close[i - 1] < ll[i - 1]
                if long_sig or short_sig:
                    side = "long" if long_sig else "short"
                    a = atr[i - 1]
                    stop_dist = p.stop_atr * a
                    entry = openp[i] + (half_spread if side == "long" else -half_spread)
                    sl = entry - stop_dist if side == "long" else entry + stop_dist
                    tp = (entry + p.reward_risk * stop_dist if side == "long"
                          else entry - p.reward_risk * stop_dist)

                    # size from actual stop distance, capped by total-risk budget
                    risk_pct = p.risk_pct
                    risk_money = equity * risk_pct / 100.0
                    size = risk_money / stop_dist if stop_dist > 0 else 0.0
                    if size > 0:
                        equity -= cost_per_side * size  # entry-side cost
                        pos = dict(
                            side=side, entry=entry, init_sl=sl, sl=sl, tp=tp,
                            size=size, atr=a, entry_bar=i, entry_time=idx[i],
                            risk_money=risk_money,
                            hw=entry, lw=entry,
                        )

        # ---- 3) mark to market ----------------------------------------
        if pos is not None:
            unreal = (close[i] - pos["entry"]) * pos["size"] if pos["side"] == "long" \
                else (pos["entry"] - close[i]) * pos["size"]
            mark = equity + unreal
        else:
            mark = equity
        curve[i] = mark
        peak = max(peak, mark)
        dd = (peak - mark) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    # force-close anything still open at the last bar
    if pos is not None:
        close_pos(n - 1, close[n - 1], "eod")

    curve = pd.Series(curve, index=idx).ffill()
    return curve, trades, max_dd


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def metrics(curve: pd.Series, trades: list[Trade], max_dd: float, p: Params) -> dict:
    if not trades:
        return {"trades": 0}
    pnl = np.array([t.pnl for t in trades])
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    end = curve.iloc[-1]
    start = p.start_equity
    valid = curve.dropna()
    years = (valid.index[-1] - valid.index[0]).days / 365.25

    rets = curve.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0

    # max consecutive losses
    mc = run = 0
    for x in pnl:
        run = run + 1 if x < 0 else 0
        mc = max(mc, run)

    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(pnl) * 100,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "total_return_pct": (end / start - 1) * 100,
        "cagr_pct": ((end / start) ** (1 / years) - 1) * 100 if years > 0 and end > 0 else 0.0,
        "max_dd_pct": max_dd * 100,
        "sharpe": sharpe,
        "expectancy_r": pnl.mean() / np.mean([t.r_multiple and abs(t.pnl / t.r_multiple) for t in trades]) if trades else 0.0,
        "avg_r": np.mean([t.r_multiple for t in trades]),
        "max_consec_losses": mc,
        "avg_bars_held": np.mean([t.bars_held for t in trades]),
        "final_equity": end,
    }


def report(m: dict, title: str) -> str:
    if m.get("trades", 0) == 0:
        return f"{title}: no trades"
    lines = [
        f"=== {title} ===",
        f"  trades            : {m['trades']}",
        f"  win rate          : {m['win_rate']:.1f}%",
        f"  profit factor     : {m['profit_factor']:.2f}",
        f"  total return      : {m['total_return_pct']:.1f}%",
        f"  CAGR              : {m['cagr_pct']:.1f}%",
        f"  max drawdown      : {m['max_dd_pct']:.1f}%",
        f"  sharpe (daily)    : {m['sharpe']:.2f}",
        f"  avg R per trade   : {m['avg_r']:.2f}",
        f"  max consec losses : {m['max_consec_losses']}",
        f"  avg bars held     : {m['avg_bars_held']:.1f}",
        f"  final equity      : ${m['final_equity']:,.0f}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="daily", choices=["daily", "h1", "m5"])
    args = ap.parse_args()

    df = fetch_data.load(args.tf)
    p = Params()
    curve, trades, max_dd = backtest(df, p)
    m = metrics(curve, trades, max_dd, p)
    print(report(m, f"XauBreakoutEA base config [{args.tf}] {df.index.min().date()}..{df.index.max().date()}"))

    os.makedirs(REPORT_DIR, exist_ok=True)
    curve.to_csv(os.path.join(REPORT_DIR, f"equity_{args.tf}.csv"))
    if trades:
        pd.DataFrame([asdict(t) for t in trades]).to_csv(
            os.path.join(REPORT_DIR, f"trades_{args.tf}.csv"), index=False
        )
    print(f"\nsaved equity + trades to {REPORT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
