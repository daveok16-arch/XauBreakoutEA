# The frequency bridge

The lesson of the $12 question was that our edge is real but slow: ~7.5 trades/yr
means a tiny account compounds over centuries. The honest route to the
small-account goal is therefore NOT a new unproven scalp - it is to make the edge
we have ALREADY PROVEN fire more often, without destroying it.

`frequency_bridge.py` tests three levers, all keeping the proven ingredients
(long-only, Donchian breakout, ATR-buffered stop, close-confirmed, one position):

## 1. Shorter lookback (daily)

```
variant   n   trades/yr  win%    avgR    PF  maxDD%     t  chunks  annEV%
N=5     506      19.4    47.2  +0.239  1.50    12.4  4.08     4/4     3.5
N=10    395      15.1    47.3  +0.258  1.58     9.9  3.80     4/4     2.9
N=20    298      11.4    50.3  +0.332  1.77     6.9  4.28     4/4     2.8
N=40    225       8.6    50.2  +0.347  1.86     8.7  3.87     4/4     2.2
N=60    196       7.5    50.5  +0.357  1.84     8.2  3.66     4/4     2.0
N=120   151       5.8    52.3  +0.410  1.99     5.9  3.72     4/4     1.8
```

Shorter lookbacks trade more AND have higher annual EV, despite lower per-trade
edge: N=5 gives 3.5%/yr vs N=60's 2.0%/yr. Every variant stays positive in all 4
chronological chunks. The per-trade edge falls (0.357 -> 0.239) but the count
rises faster (7.5 -> 19.4), so the product rises. This is the whole point.

## 2. Timeframe (the big lever)

```
H1, 2.4 years (2024-05..2026-10)
variant   n   trades/yr  win%    avgR    PF  maxDD%     t  chunks  annEV%
N=5     751     313.5    44.3  +0.163  1.31    12.0  3.42     4/4    38.3
N=10    588     245.4    45.2  +0.173  1.33    10.0  3.21     4/4    31.8
N=20    448     187.0    44.9  +0.152  1.29    13.2  2.49     4/4    21.4
N=40    348     145.3    45.1  +0.156  1.31    10.8  2.26     4/4    17.0
N=60    285     119.0    46.3  +0.208  1.44     8.7  2.71     4/4    18.6
N=120   231      96.4    48.1  +0.231  1.51     7.4  2.71     4/4    16.7
```

H1 gives 17-38%/yr annual EV at 0.75% risk - roughly 10-20x the daily figure.
All positive in all chunks. Caveat: only 2.4 years of H1 data, so the t-stats
(2.3-3.4) are decent but the sample is short; treat the magnitude as promising,
not settled.

## 3. Channels (several lookbacks at once)

Running N=10, N=20 and N=60 together pools 889 daily trades (34.1/yr, combined
t=6.74, 4/4 chunks, annEV 7.8%) or 1321 H1 trades (551/yr, t=4.86, annEV 71.8%).
The channels are correlated (same edge), so this is NOT free diversification - a
shared risk budget would not let all three take full size at once. The honest
reading: channels add frequency, not independent edge.

## Cost sensitivity (does the extra frequency pay for its spread?)

```
H1          spread 0.30   spread 0.60   spread 0.90   spread 1.20
N=5   annEV%      38.3         33.3          28.4          20.6
N=20 annEV%       21.4         18.4          15.0          11.7
N=60 annEV%       18.6         17.1          14.2          12.7
```

The H1 variants survive even a 1.20 spread - and 0.60 is a pessimistic number
(daily gold is ~0.30; H1 in liquid hours is similar, in thin hours wider). So the
frequency gain is robust to plausible costs. Daily N=5 degrades from 3.5% to 2.3%
across the same range. Notably, at wide spreads N=5's edge advantage over N=20
shrinks (both drop), so at very high cost the higher-frequency variant is the more
fragile one - the expected direction.

## Closing the loop: $12 -> $5,000, bootstrapped on the ACTUAL R distribution

Not a normal approximation - resampling the real per-trade R pool, fixed-fraction
sizing:

```
variant    trades/yr   risk   P(reach)  P(ruin)  median years
daily N=60      7.5    0.75%     100%      0%         288
daily N=60      7.5    3.00%     100%      0%          77
daily N=5      19.4    0.75%     100%      0%         182
daily N=5      19.4    3.00%    99.9%    0.1%          50
h1 N=5        313.5    0.75%     100%      0%          17
h1 N=5        313.5    3.00%    99.8%    0.2%           5
h1 N=20       187.0    0.75%     100%      0%          30
h1 N=20       187.0    3.00%    99.4%    0.6%           9
```

This is the answer to the $12 question using our own proven edge. Moving from the
production daily N=60 to an H1 N=5 variant cuts the median time from **288 years
to 17 years** at the same 0.75% risk - or **5 years at 3% risk** - while staying
long-only, single-position and fixed-fraction (no martingale, recovery corr 0 by
construction). The edge is the same edge; it simply fires ~40x more often.

## Verdict

The frequency bridge works. The proven long-only breakout edge can be made to
fire far more often without inventing a new, unproven mechanism:

1. Use a shorter lookback (N=5-20) rather than the production N=60.
2. Move to H1, where the same edge fires ~100-300x/yr.
3. Both raise ANNUAL EV even though per-trade edge falls.

This turns the $12 goal from ~300 years into a realistic horizon (5-17 years) using
nothing but the edge we already proved. The remaining caveats are real and should
be stated: the H1 history is only 2.4 years, the combined-channel EV ignores the
shared risk budget, and the production EA currently hard-codes N=60 with no
lookback input, so adopting this needs a deliberate EA change (not done here -
production stays untouched).
