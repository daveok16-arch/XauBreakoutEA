# EV: where the edge actually comes from

One mechanism, decomposed. No new strategies. The question is not "what else
could we test" but "what is proven, and where does the expectancy live."

`python3 research/ev_decomposition.py --tf daily`

An angle is called **PROVEN** only if it has n >= 30, a one-sided t-stat >= 1.65
on per-trade R, and a positive mean in every chronological chunk. Anything else
is NOT PROVEN or INCONCLUSIVE. Exit-reason buckets are marked descriptive
because they are deterministic by rule (a target is always ~+2R, a stop ~-1R),
so a t-test on them would be a tautology.

## The decomposition (26-year daily)

```
bucket                    n   win%    avgR     PF      t   verdict
ALL                     267   46.1   0.240   1.50   2.91  PROVEN
side=long               196   50.5   0.357   1.81   3.66  PROVEN
side=short               71   33.8  -0.084   0.86  -0.57  NOT PROVEN (zero)
exit=stop               174   17.2  -0.691   0.06          (descriptive)
exit=target              93  100.0   1.981    inf          (descriptive)
hold=shortest-25%        55   21.8  -0.369   0.54  -2.19  NEGATIVE (loses)
hold=25-50%              70   47.1   0.224   1.49   1.42  NOT PROVEN
hold=50-75%              60   40.0   0.158   1.32   0.93  NOT PROVEN
hold=longest-25%         82   65.9   0.721   3.60   5.05  PROVEN
```

The H1 (production timeframe) shows the same shape: long side positive, short
side indistinguishable from zero, short holds reliably losing, long holds
strongly positive.

## The one proven angle

**Long-only breakout on daily gold, held for long excursions.**

- 196 trades over 26 years, avg +0.357R, PF 1.84, t = 3.66
- positive in every chronological chunk
- the short side and quick exits are where the losses live; removing them is not
  curve-fitting, it is removing a reliably negative component

## The benchmark that reframes it

```
=== vs buy-and-hold [daily] 2000-2026 (26.1y) ===
  buy & hold gold        CAGR  11.0%  maxDD  44.4%
  breakout long+short    CAGR   1.7%  maxDD  12.5%  PF 1.53  avgR +0.240
  breakout long-only     CAGR   1.9%  maxDD   8.2%  PF 1.84  avgR +0.357

=== vs buy-and-hold [h1] 2024-2026 (2.4y) ===
  buy & hold gold        CAGR  26.7%  maxDD  29.0%
  breakout long+short    CAGR  23.6%  maxDD  11.1%  PF 1.37  avgR +0.173
  breakout long-only     CAGR  18.3%  maxDD   8.7%  PF 1.44  avgR +0.208
```

This is the honest verdict: **the strategy does not beat holding gold on
return. It beats it on drawdown.**

- Daily: 1.9% vs 11.0% CAGR, but 8.2% vs 44.4% max drawdown.
- H1: 18.3% vs 26.7% CAGR, but 8.7% vs 29.0% max drawdown - and the 2.4-year
  window is a violent gold bull market, which is why the 40% headline existed.

So the value proposition is **a lower-drawdown way to hold gold**, not a return
multiplier. Anyone expecting the EA to beat buy-and-hold will be disappointed;
anyone wanting trend exposure with a fraction of the drawdown has a real thing.

## Two corroborating signals

**Lookback is monotonic, and longer is better:**

```
  20: +0.157    60: +0.240   180: +0.364
  40: +0.175   120: +0.359   250: +0.460
```

No peak to fit - the edge keeps improving as the horizon lengthens. That is
consistent with the mechanism being genuine long-horizon trend-following, not a
tuned artifact. It also means the current default (60) is not where the edge is
strongest.

**Parameter sensitivity is smooth**, not spiky: stop 1.0-1.5ATR fine, RR 2.0-4.0
fine, ATR period barely matters. A fragile edge shows a knife-edge optimum; this
does not.

## What this means for scope

We are not building a multi-angle system. We have **one proven angle**:

> long-only breakout / trend-following on gold, with a drawdown-reducing exit
> scheme.

Everything else we tried (short side, H1+H4 stacking, trailing TP) either adds
no edge or adds correlated leverage. The honest EA is a focused long-only trend
system, sold on drawdown control - not the "40% CAGR" that the bull market
flattered.

## Why not more trades / scalping?

A recurring question: instead of one position at a time, why not open many trades
and scalp to grow the account? The earlier version of this section claimed the
M5 sample showed scalping "dies", citing CAGR -34%. That was wrong to assert:
the M5 sample available at the time was only 2.4 MONTHS, so the number was noise,
and a limitation of our breakout mechanism says nothing about scalping in
general. Corrected here.

What the fixed breakout logic does show across horizons (same mechanism, so this
is about our edge, not about scalping as a class):

```
timeframe   trades/yr   avg R/trade   PF
daily             10       +0.240     1.53
H1               183       +0.173     1.37
M5 (2.4mo only)  149       +0.008     1.00   <- sample too short to conclude
```

The lookback sweep is monotonic (20 bars -> +0.157R, 250 bars -> +0.460R), so
this particular trend edge does weaken as the horizon shortens. That is a fact
about *this mechanism*. A different, faster mechanism can carry a different edge.

Small-account growth is a separate question, and growth_math.py shows it is
feasible given a real edge: the broker minimum lot forces large early leverage,
which compounds a genuine edge fast. From $3 to $5,000 at 1 oz min lot, 3% risk:

```
win   R:R   edge/trade   P(reach)   P(ruin)
0.50  1.5     +0.250      95.8%      4.2%
0.45  2.0     +0.350      96.3%      3.7%
0.50  1.0     +0.000       0.0%    100.0%
```

So the question is not whether $3 -> $5,000 is possible (it is), but whether a
given EA has a genuine, sustained net edge per trade (~+0.2R or better). A
martingale/recovery EA produces a similar early curve with ruin hidden in the
tail, which is why the mechanism - not the curve - is the discriminator.

## The fast-scalper mechanism, stated fairly

The mechanism behind the small-account EAs that grow $3-$10 to thousands:

1. start at the broker minimum lot on a small account
2. **step the lot size up in levels as the account grows** (balance tiers)
3. scalp fast: many trades, very short holds, open and close almost at once

Balance-tiered sizing is COMPOUNDING (size tracks equity). It is NOT recovery
martingale (size tracks losses). Different mechanisms; this section is about the
first, and it is legitimate.

What decides everything is one number: the break-even win rate after spread.
For TP, SL and round-trip spread s (same units):

    p* = (SL + s) / (TP + SL)

`python3 research/scalp_ev.py --table` prints it across a grid:

```
   TP    SL | spread=0.1   spread=0.2   spread=0.3
  0.2   0.5 |     85.7%       100.0%       114.3%
  0.3   1.0 |     84.6%        92.3%       100.0%
  0.5   1.0 |     73.3%        80.0%        86.7%
  1.0   1.0 |     55.0%        60.0%        65.0%
  2.0   1.0 |     36.7%        40.0%        43.3%
```

Tight TP with a wide spread pushes the required win rate toward and past 100%.
A scalper needs a mechanism that genuinely wins more often than p*.

Tiered sizing does not change this - it changes how fast you compound, or bleed.
Simulated ($10 start, tiered lots 0.01->0.2, 12,500 scalps):

```
edge +6.25% of risked $  ->  median $10 -> $19.36,  P(ruin) 0.0%
edge -6.25% of risked $  ->  median $10 -> $5.00,   P(ruin) 100%
```

So the design is coherent and the growth is real *if* the scalp edge clears
break-even. The thing to measure is not the curve (a recovery EA can fake one),
but the win rate vs p*, and whether size steps up with *equity* (compounding) or
with *losses* (recovery). `gold_reaper_analysis.py` measures the latter.

## How this differs from our EA

| | our breakout EA | fast tiered scalper |
|---|---|---|
| frequency | ~10/yr (daily) | many per day |
| sizing | fixed % of equity, from stop distance | min lot, stepped up by equity tiers |
| sizing basis | risk (stop) | equity level (compounding) |
| edge source | long-horizon trend | short-horizon mean reversion / momentum |
| cost sensitivity | low (~1% of R) | high (spread vs tight TP) |
| product | drawdown control | fast compounding on a small account |

Both are legitimate designs. They differ in where the edge comes from and in how
much they depend on the scalp win rate clearing break-even after spread.

## Next step, in order

1. Confirm the long-only daily result survives costs and the OOS/regime gate on
   the real (non-proxy) instrument - this is what the Deriv H1 export is for.
2. If it does, the production EA becomes a long-only trend system. That is a
   smaller, more honest, more defensible product than what we started with.
