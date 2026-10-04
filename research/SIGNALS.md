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
