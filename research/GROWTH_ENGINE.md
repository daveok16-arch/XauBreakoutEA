# The growth engine: lot levelling + trade scaling

The user's question, stated mechanically: will an account actually GROW if, as
equity rises, (a) the lot size levels up and (b) the number of trades increases?

Yes - and those are two different levers. `growth_engine.py` runs both on the real
per-trade R pool of the proven long-only edge, so nothing here assumes an edge; it
compounds the one we already proved.

## The two levers behave differently

```
daily N=60, $12 -> $5,000, target risk 0.75%, micro min-lot risk $1.86
engine                          P(reach)  P(ruin)  median yrs  medDD%
lot levelling only                 79.5%    20.5%       198.5    38.3
lot levelling + trades x equity^.5 79.5%    20.5%        38.4    38.3
lot levelling + trades x equity^1.0 79.5%    20.5%        27.9    38.3
```

- **Trade scaling is a pure calendar lever.** It cut the median from 198 years to
  38 (slow scaling) or 28 (aggressive) - a 5-7x speed-up - while P(reach)/P(ruin)
  and median drawdown stayed EXACTLY the same. More trades of the same edge move
  the clock, not the odds. This is the mechanism the user described, and it works.
- **Lot levelling is just compounding** (continuous fixed-fraction already does it;
  discrete levels are a coarser version). It changes the SIZE of the moves, not
  the direction of the odds.

## The real killer is the broker's MINIMUM LOT, not the strategy

Run H1 N=5 (313 trades/yr) at a $12 start and the outcome depends entirely on how
big one minimum lot is:

```
h1 N=5, $12 -> $5,000
min-lot $   target risk   P(reach)  P(ruin)  median yrs   account
   1.86        0.75%         53.0%    47.0%        2.0     micro  (10 oz/lot)
   1.86        0.25%         53.0%    47.0%        3.6     micro
   0.19        0.75%         99.8%     0.2%        4.8     cent   (1 oz/lot)
   0.19        0.25%         99.8%     0.2%       10.0     cent
```

On a micro account, one minimum lot risks $1.86 = 15.5% of a $12 balance. That
floor FORCES a huge risk on every trade until equity grows, and no target-risk
setting can lower it - so ruin is ~47%. On a cent account the min lot risks $0.19
= 1.6%, the floor never binds, and ruin collapses to 0.2%.

Conclusion: **the same strategy, same edge, is a coin-flip on a micro account and
a near-certainty on a cent account.** The instrument contract size decides whether
the growth engine survives its own start.

## Putting it together: the engine at survival risk (cent account)

```
variant      trades/yr  P(reach)  P(ruin)  median years
daily N=60       7.5      100.0%     0.0%          189
daily N=5       19.4      100.0%     0.0%          109
h1 N=20        187.0       99.8%     0.2%           18
h1 N=5         313.5       99.8%     0.2%           10
```

Same edge, same long-only/single-position/fixed-fraction discipline, no
martingale - just lot levelling plus trade scaling. The account grows, and the
timeframe is what decides how fast.

## Verdict

1. The growth engine (lot levelling + trade scaling) works, and trade scaling is
   the powerful half: it multiplies the calendar, not the risk.
2. Whether it SURVIVES depends on the broker's minimum lot. A $12 account must be
   on a CENT (1 oz/lot) instrument; on a micro (10 oz/lot) the floor forces ~15%
   risk per trade and ruin is ~47%.
3. The edge itself is unchanged - this is our proven long-only breakout, just
   firing more often and sizing up as equity grows.

Caveats: H1 history is 2.4 years, so the H1 magnitudes are promising not settled;
the trade-scaling curve (equity^0.5) is a design choice, and more concurrent
trades would need a shared risk budget (not modelled). Production EA untouched.
