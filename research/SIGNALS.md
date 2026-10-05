# MQL5 signals: what the numbers actually say

Date: 2026-10-03. Source: MQL5 Signals service, public pages only.
Reproduce with `python3 research/signals_scan.py --pages 2`.

## Method

The MQL5 "Growth %" figure on a signal's header is not a return on deposits - it
is distorted by deposits and withdrawals and can show five figures for an account
that has been bled down. So instead of trusting it, this scan pulls each signal's
published `equityData` curve and recomputes:

- **max drawdown** from the balance curve (peak-to-trough, our own calculation)
- **CAGR** from first to last balance over the elapsed time
- **flags** for patterns that make a signal uncopyable in practice

## Findings

22 gold-focused signals scored. Sorted by CAGR/drawdown.

| Signal | Weeks | Trades | Win % | Header "growth" | Max DD | CAGR | Flag |
|---|---|---|---|---|---|---|---|
| Giaphat GOLD Vantage | 35 | 889 | 80.0 | 288% | 5.4% | 3753% | <1yr |
| XAUUSD Breakouts High Risk | 37 | 280 | 72.5 | 268% | 70.1% | 16932% | HIGH-DD |
| MK Gold3Plus | 6 | 246 | 61.0 | 78% | 34.2% | 2911% | <1yr |
| GoldCyle I | 19 | 86 | 59.3 | 323% | 6.4% | 525% | <1yr |
| Aura Gold Pro (FPMarkets) | 37 | 465 | 62.1 | 736% | 17.9% | 356% | <1yr |
| GOLD HUAT EA | 165 | 690 | 55.1 | 350% | 15.2% | 162% | ok |
| MSC Gold Stable Pro | 128 | 1150 | 82.2 | 1483% | 15.4% | 114% | heavy-lev |
| **Gold Reaper New V2 2** | **101** | **882** | **72.3** | **345%** | **16.8%** | **110%** | **ok** |
| MSC Gold Invest Pro | 172 | 1726 | 79.4 | 1104% | 30.0% | 63% | ok |
| Gold Minion | 151 | 723 | 57.1 | 566% | 29.7% | 202% | long-loss-streak |
| GoldWave signal | 70 | 297 | **95.3** | 760% | **84.7%** | 196% | MARTINGALE? |
| The Gold Reaper Live | 139 | 1335 | 72.4 | 278% | 45.6% | 65% | HIGH-DD |
| Pure Gold 2000 Vantage | 30 | 671 | 53.8 | 283% | 40.2% | 89% | HIGH-DD, <1yr |
| MSC SuperGold Pro | 98 | 3012 | 77.0 | **24179%** | **61.5%** | **-10.2%** | HIGH-DD |
| Gold Breakout PRO All Star | 39 | 117 | 68.4 | 1368% | **85.4%** | 3.7% | HIGH-DD, <1yr |
| Aegis Gold | 94 | 1523 | 63.6 | 286% | 38.9% | -2.8% | heavy-lev |

(Full 22 rows in `reports/signals_scan.csv`.)

## The three traps

**1. Header growth is meaningless.** MSC SuperGold Pro advertises **24,179%**
growth. Its recomputed CAGR is **-10.2%** and its balance has fallen to $934
after $5,343 of withdrawals. The five-figure number is a withdrawal artefact,
not performance.

**2. A 95% win rate is a warning, not a selling point.** GoldWave shows 95.3%
wins with 297 trades and only 14 losses - and an **84.7% drawdown**. You cannot
win 95% of breakout trades honestly; that pattern is martingale/averaging, where
the rare loss is enormous. Same shape on XAUUSD AI trade (69% wins, 57.7% DD)
and Gold Breakout PRO (85.4% DD).

**3. Short histories dominate the top of the list.** The highest CAGR/drawdown
rows are all under a year. A 19-week curve has not seen a regime change.

## What survives

Applying the filter honestly, very little does:

- **Gold Reaper New V2 2** - 101 weeks, 882 trades, real account, 16.8% DD,
  ~110% CAGR, Sharpe 0.23. It is the best gold signal here on risk-adjusted
  return, and it is not martingale-shaped.
- **GOLD HUAT EA** (165 weeks, 15.2% DD) and **MSC Gold Stable Pro**
  (128 weeks, 15.4% DD) are the other long-lived, low-drawdown options.

## The part the numbers don't show: copying it

This is where signal-following actually fails.

- **Slippage is real and confirmed by subscribers.** A current subscriber review
  on Gold Reaper states: *"execution slippage lets me have really low profits so
  far. sometimes even losses when there is a profit shown here."* The signal's
  numbers are the provider's fills, not yours.
- **Deriv allows only one signal per MT5 account**, and once subscribed you
  **cannot trade that account manually**. So a signal is an all-in commitment of
  one account.
- **MQL5 will not let you subscribe to a signal using leverage above 1:500.**
  Deriv offers up to 1:1000, so check the signal's leverage before assuming it
  is available.
- The provider's equity curve is an **average** outcome. Your result depends on
  your broker's spread, latency, and lot-scaling - the exact gap the subscriber
  above hit.

## Deep dive: Gold Reaper V2 (our benchmark)

Reverse-engineered from its public pages and published balance curve.
Reproduce with `python3 research/gold_reaper_analysis.py`.

### What it actually is

Gold Reaper is not a signal-first product - it is an **EA being sold on the
MQL5 Market** (product 111357, $949, published Feb 2024, v5.1, 119 purchases/
month). The signal is the vendor's own live/demo account. The vendor's own
description:

> "trading breakouts of important support and resistance levels ... All trades
> have a stoploss and takeprofit, but also use a trailing stoploss and trailing
> takeprofit ... No grid / No Martingale / No risky risk management."

So it is the **same core edge we built** (gold breakout of S/R), executed with
more machinery around it.

### Its documented structure

| Element | Gold Reaper | Our EA |
|---|---|---|
| Core edge | breakout of S/R | breakout of S/R (Donchian) |
| Timeframes | **multiple at once** | one |
| Internal strategies | **several, risk-spread** | one |
| Stop / target | SL + TP + trailing SL + **trailing TP** | SL + TP + trailing SL |
| Sizing anchor | **max allowed DD setting** vs strategy's historical max DD | fixed 0.75% per trade |
| Frequency | auto from balance + max DD | fixed |
| News filter | **NFP filter** (+ auto GMT) | calendar blackout |
| Weekend | Friday stop hour | Friday stop hour |
| Anti-correlation | entry/exit/trail randomisation | none |
| Chart timeframe | H1 | H1 |
| Min balance | $600 | - |

The notable design choice is **sizing**: you set a maximum allowed drawdown, and
the EA sizes positions so that its historical worst drawdown maps onto your
budget. That is a different paradigm from fixed-fractional risk, and it is
honest - it does not promise more than the account can bear.

### Did we confirm "no martingale"?

Yes, from the published balance curve (868 reconstructed balance steps):

| Metric | Value | Reads as |
|---|---|---|
| wins / losses | 409 / 459 | ~47% win rate |
| avg win / avg loss | $21.70 / $8.20 | **2.65 reward:risk** |
| longest loss run | 11 | survivable |
| loss as % of balance by quartile | 0.37 / 0.19 / 0.22 / 0.30 | **flat** = fixed-fractional |
| win as % of balance by quartile | 0.62 / 0.66 / 0.68 / 0.61 | flat |
| corr(drawdown depth, loss size) | +0.30 | weak, not martingale |

The engine of the returns is **reward:risk (2.65)**, not win rate and not
escalating size. Losses stay roughly constant as a share of balance across the
whole life of the account, which is exactly what fixed-fractional sizing looks
like and the opposite of martingale. The +0.30 correlation is mild and mostly a
small-account/minimum-lot artefact early on, where a $1,600 account cannot size
below the broker minimum.

### What this means for our targets

- The **~110% CAGR is real but it is bought with ~30% drawdown** (the vendor
  states a 30% max DD; our balance-curve recomputation showed 16.8%, so equity
  DD is the higher, truer figure). It is not a low-risk curve.
- Our EA's modelled 12.5% drawdown at ~1.7% CAGR is far more conservative. The
  honest gap is **not** the strategy - it is the **risk budget and the R:R**.
  Gold Reaper risks multiples of what we do per trade and lets winners run with
  a trailing TP.
- The single most portable idea is the **trailing TP** and the
  **max-drawdown-anchored sizing**. Both are straightforward to add to our EA.

### The copying warning, quantified

The signal page lists per-broker slippage for real subscriber accounts. Most
show 0.00, but one (UltimaMarkets-Live 1) shows 0.60 pips, and subscriber
reviews report the gap directly. The page's own advice is to **run the EA rather
than copy the signal**: "There will be less slippage this way, and the EA will
fully adapt to your account balance." That is the vendor conceding the copying
problem.

## Recommendation


Use signals as a **benchmark**, not a product to buy.

1. Our own XauBreakoutEA already targets the same edge (gold breakout, ATR stop,
   percent risk) with a validated ~1.5 profit factor and 12.5% modelled
   drawdown - deliberately without the martingale tail that ruins most of the
   high-growth signals above.
2. The honest bar to beat is **Gold Reaper: 16.8% DD, ~110% CAGR over 101
   weeks**. If our EA cannot approach that on real Deriv data, it is not yet
   finished.
3. If you ever do copy a signal, copy a long-lived, low-drawdown one
   (Gold Reaper, GOLD HUAT) and expect your own fills to be worse than the page.

The scan is repeatable, so this judgement can be re-checked as new signals
appear rather than taken on trust.
