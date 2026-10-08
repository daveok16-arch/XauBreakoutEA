# DowGold EA - assessment

Evaluated from public sources (dowgoldea.com, its FAQ, the Telegram channel, the
MyFXBook member profile, and two independent reseller/review pages). This is a
marketing-claims review plus a risk-math check; no trade list was available.

## What it is (a different archetype again)

DowGold is a cloud-connected MT4/MT5 EA for Gold (XAUUSD), US30 and optional
Silver (XAGUSD). The EA on your account is a thin executor; the strategy lives on
the vendor's servers and streams decisions in. Four risk modes (Flipping,
Aggressive, Balanced, Prop Firm). This is NOT the same as Gold Reaper (single-
instrument, self-contained) or ours (single-instrument, one direction, holds).

## Claims that check out / are in its favour

- Public, verified MyFXBook accounts exist (myfxbook.com/members/DowGoldHS), some
  with withdrawal history. More than most EAs offer.
- A free backtest-only version is published - you can test it yourself in the MT5
  Strategy Tester before paying. That is genuinely testable.
- Gold is stated as single-order, no grid, no martingale, with a hard max loss and
  a news filter. If true, that removes the single biggest blow-up mechanism.
- It states honest caveats on the +315% day ("exceptional, not the norm", "0%
  drawdown was specific to that fast trade"). That is unusually candid.
- One public account shows +93.30% with 26.98% drawdown at 1:1000 leverage.

## Red flags

1. Headline contradiction with its own risk list. The banner says "No grid. No
   martingale." The detail says optional Silver AND optional Turbo use "controlled
   grid recovery". Both are opt-in and off by default, but the headline omits
   them. "Controlled, capped, never blind doubling" is still grid recovery.

2. Contradiction on small accounts. The Telegram ad says "No demo or cent
   accounts." The site says "Works with balances as small as $50 on a standard
   account, or $5 on a cent account." Both cannot be true.

3. Return claims imply far bigger drawdowns than advertised. Taking their own
   numbers (100-200%/month, "double in less than 5 days", "worst-case DD 30-40%")
   and a realistic edge (55% win, 1.5R = +0.375R/trade, ~21 trades/month):

```
claim                risk/trade   median maxDD   P(ruin)
Balanced 10-30%/mo        3.4%          23.0%       0.0%
Aggressive 40-80%/mo      6.0%          38.7%       0.0%
Flipping 100-200%/mo      8.9%          52.8%       0.1%
Flipping 200%+/mo        14.3%          73.0%       1.7%
```

   To hit 100-200%/month you must risk ~9-14% of equity per trade, and the
   resulting median drawdown is 53-73% - not the "30-40% worst-case" claimed. The
   drawdown claim is optimistic by roughly 2x. This is the same arithmetic as our
   own growth_math: high monthly return and low drawdown are not simultaneously
   available.

4. Cherry-picked windows and account resets. The proof points are the best
   windows: +315% in 1 day, +101% in 5 days, +95% in 7 days. Their own FAQ says
   once an account doubles they withdraw and "start fresh". A reset resets the
   drawdown statistics too, so the surviving public history is biased upward. The
   $50 "freedom" account is +144% but is $50 -> $122 - a tiny base, so the
   percentage is noise-dominated.

5. "0% drawdown" is misleading framing (a single day that ran straight up), which
   they do partly caveat. Still used as a headline.

6. Cloud dependency is a real risk, not just marketing. If the servers stop, the
   EA stops - they acknowledge this. You are renting the brain, not owning it.

7. 1:1000 leverage on a public account is an offshore-broker signal, and 1:1000
   is what makes "double in 5 days" arithmetically possible at all.

8. Closed source and not on MQL5 by design, so nothing can be independently
   audited; the track record is the only evidence.

## How it compares to what we have

| | ours | Gold Reaper | DowGold |
|---|---|---|---|
| instruments | Gold, 1 way | Gold | Gold + US30 + Silver |
| logic location | local EA | local EA | vendor cloud |
| cadence | hold ~5 days | ~1.24 closes/day | mode-dependent |
| Gold risk | single order | multi-position | single order (claimed) |
| optional grid | no | n/a | yes (Silver/Turbo, opt-in) |
| evidence | 26y backtest | live curve | live accounts, cherry-picked |

DowGold's "Flipping" mode is the same object as the fast-scalper we modeled: high
frequency x high leverage. The +315% day is exactly the rare big-move lottery we
showed earlier - real, but not repeatable, and the mode's own worst case is the
ruin zone.

## Verdict

More credible than the average EA (public verified accounts, a testable free
build, candid caveats), but the marketing overstates it in specific, checkable
ways: the headline hides opt-in grid recovery, the return claims imply 2x the
drawdown they advertise, and the proof is cherry-picked winning windows plus
account resets. It is not a scam on its face; it is a high-risk product sold with
optimistic framing.

What would settle it: the free backtest build run in a real MT5 Strategy Tester
over a long Gold history (including 2013 and 2020), and the full MyFXBook trade
list with drawdown left intact. Until then, treat the advertised drawdowns as
roughly half the real ones.
