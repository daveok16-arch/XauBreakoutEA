# Where this project stands

A plain statement of what is proven, what is not, what is blocked, and what
"production" can mean. Kept deliberately blunt.

## Proven

- **26-year daily/weekly study**: 320 trades, PF 1.66, ~2.5% CAGR, positive in
  6/6 regime folds. This is the only result I would call credible. It is also a
  *different system* from the production EA, on a much slower timeframe.
- **Engine exactness**: the research engine reproduces the single-leg H1 result
  exactly (439/439 trades). The harness measures what it claims to measure.
- **Infrastructure integrity**: the pipeline can return BLOCKED and INCONCLUSIVE
  rather than manufacture confidence. That property is real and tested.

## Unproven

- **2.4-year H1 (the production EA's own timeframe)**: PF 1.38. Thin, one
  regime, from a futures proxy. Not evidence of a durable edge.
- **H1+H4 combined 40.1% CAGR**: seductive and **not evidence** - the legs are
  ~99% same-direction correlated and the shared risk budget never bound. It is
  leverage, not diversification.
- **Trailing TP**: negative on the data we have.

The pattern: a modest, credible edge on a slow timeframe; an unproven edge on
the timeframe we would actually ship.

## Blocked

The long-history gate needs **8+ years of spot XAUUSD H1**. We do not have it.

- The only H1 we hold is 2.4 years, and it is a COMEX futures proxy (`GC=F`).
- Spot history exists but every route is unreachable from the research sandbox:
  Deriv's websocket (Cloudflare 520), Stooq (datacenter IP), Dukascopy (no
  route). Yahoo carries no spot gold, only the futures proxy.

**The Deriv API is the best source** (actual instrument, true-UTC epochs). The
depth probe must be run from a network that can reach `ws.derivws.com`:

```
python3 research/deriv_fetch.py --probe --symbol frxXAUUSD
```

That one command decides which branch below we are in.

## The decision tree

```
Deriv H1 export / API fetch
   |
   +-- history < 8 years?  -> gate cannot clear from Deriv alone.
   |                          Either pair Deriv + a deep source (Dukascopy),
   |                          or stop and call the research done.
   |
   +-- history >= 8 years, >= 2 regimes?
          |
          +-- OOS >= 75% positive folds AND combined DD not worse?
                 |
                 +-- YES -> a validated H1 or H1+H4 strategy exists.
                 |          Expect modest returns, not the 40% headline.
                 |          Now production questions become real.
                 |
                 +-- NO  -> the edge did not survive. Correct outcome;
                            the pipeline did its job.
```

## What "production" can mean

These are very different projects and the heading differs for each:

1. **Personal trading, own capital.** The bar is "beats holding gold after real
   costs." A modest edge can be enough. This is the most reachable destination.
2. **A published/sold EA.** The bar is a *live track record*, because an honest
   EA cannot be sold on a backtest - that would make it exactly what we set out
   not to be. Much harder, and mostly a business problem, not a research one.
3. **A research/credibility exercise.** The infrastructure is the deliverable,
   and it is nearly done.

## What production still requires (none of it started)

Everything built so far is backtest-side. Real deployment needs:

- MT5 Strategy Tester validation (a different engine and fill model from the
  Python harness)
- Real execution costs: spread widening at news/rollover, slippage, CFD swap,
  weekend gaps
- Reconciliation of the spot-vs-futures data problem against the live instrument
- Position sizing, drawdown controls, kill switches, monitoring
- For a product: a live track record

## The next single action

```
python3 research/deriv_fetch.py --probe --symbol frxXAUUSD
```

Nothing else is worth doing until that number is known. No further strategy
features, no EA changes, no interpreting the 2-year number. The production EA
(`Experts/`, `Include/`) stays untouched until the chain passes.
