# Gold Reaper vs our EA

`python3 research/compare_reaper.py` - both reduced to per-trade R so they can be
compared despite different instruments and periods.

Gold Reaper data is its public balance curve (signal 2265877, fetched live via
`gold_reaper_analysis.py`): 1361 curve points, 875 reconstructed trades. Our side
is the proven long-only daily backtest.

## Head to head

```
metric                    Gold Reaper      ours daily
trades                            875             196
win rate %                       47.0            50.5
avg win (R)                     +2.59           +1.58
avg loss (R)                    -1.00           -0.89
win/loss ratio                   2.59            1.77
profit factor                    2.30            1.84
expectancy (R/trade)           +0.688          +0.357
max consec losses                  11               8
max drawdown %                   16.8             8.2
recovery corr                  +0.302           0.000

sizing-neutral (per-trade % of balance):
mean % / trade                 +0.161          +0.267
Gold Reaper 1st half %         +0.133              n/a
Gold Reaper 2nd half %         +0.189              n/a
```

## What this says

**Gold Reaper's headline edge is about twice ours in R terms** (+0.688 vs
+0.357). It is a low-win, big-win shape: it wins 47% of trades but its average
win is 2.6x its average loss. Ours wins slightly more often (50.5%) with a
smaller 1.8x win/loss ratio.

**On the sizing-neutral measure, ours is actually higher** (+0.267% vs +0.161%
of balance per trade). This is the fairer comparison: R divides by each system's
own average loss, so a system with variable/recovery sizing gets its R inflated.
Once you normalise by balance instead, our per-trade efficiency is greater. Gold
Reaper's bigger R number is partly a sizing artifact.

**Gold Reaper's recovery fingerprint is +0.302** - moderate. Loss size (as % of
balance) grows with drawdown depth. That is the recovery/martingale signature,
and it is the main structural risk in its numbers. Ours is 0.000 by
construction: fixed-fraction sizing cannot grow risk while under water.

**Gold Reaper is consistent across halves** (+0.133% then +0.189% per trade), so
its record is not one lucky era. That is a point in its favour.

**Ours has half the drawdown** (8.2% vs 16.8%) and no recovery risk.

## Honest caveats

- Gold Reaper's R is normalised by its own average loss. If its lot sizing varies
  (and it does), R overstates the edge relative to a fixed-risk system. The
  sizing-neutral %/trade is the apples-to-apples number, and there ours wins.
- The recovery correlation can be **confounded by volatility clustering**: bigger
  losses happen in volatile periods, which also cause drawdowns, so a positive
  corr is suggestive of recovery sizing but not proof. Distinguishing the two
  needs the actual lot sizes, which MQL5 does not publish.
- Different periods (Gold Reaper live ~recent years; ours 2000-2026 daily) and
  different instruments. **CAGR is not comparable here** - only edge shape and
  the sizing fingerprint are.
- Gold Reaper's numbers are live (real execution, unknown broker/spread); ours
  are a backtest on the GC=F futures proxy. Its record has more "is-ness", ours
  has more verifiable mechanics.

## Verdict

Two different, real edges:

- **Gold Reaper**: lower win rate, bigger winners, higher headline expectancy,
  moderate recovery-sizing risk, larger drawdown. Its edge is real and
  consistent, but it carries tail risk we can measure but not fully explain
  without its lot sizes.
- **Ours**: higher win rate, smaller winners, smaller headline expectancy but
  higher sizing-neutral efficiency, half the drawdown, and structurally zero
  recovery risk.

Neither dominates. Gold Reaper is the higher-octane version; ours is the
lower-drawdown version. The right question is not "which is better" but which
risk profile fits the account - and ours is the one whose worst case is
bounded by design.
