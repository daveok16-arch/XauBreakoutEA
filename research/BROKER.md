# Broker-agnostic detection

The EV must not be built for one broker. Contract size, lot step, tick value and
cost differ by broker and by account type (100 oz standard, 10 oz micro, 1 oz
cent), and every EV number depends on them. So nothing is hard-coded: the spec is
detected at init and everything is derived from it.

## What is detected

All from MetaTrader 5 `SymbolInfo*` calls - no broker names, no symbol suffixes:

| field | MT5 source |
|---|---|
| contract_size | `SYMBOL_TRADE_CONTRACT_SIZE` |
| min_lot / lot_step / max_lot | `SYMBOL_VOLUME_MIN/STEP/MAX` |
| tick_size / tick_value | `SYMBOL_TRADE_TICK_SIZE` / `TICK_VALUE` |
| point / digits | `SYMBOL_POINT` / `SYMBOL_DIGITS` |
| spread_points | `(ASK - BID) / POINT` (sampled live) |
| stops_level_points | `SYMBOL_TRADE_STOPS_LEVEL` |
| commission_per_lot | average from closed-deal history (`DEAL_COMMISSION`) |
| account_equity / currency | `ACCOUNT_EQUITY` / `ACCOUNT_CURRENCY` |

The EA already sized from tick value (`RiskManager`), so its sizing was already
contract-size agnostic. What was missing was cost (spread + commission) being
detected and surfaced for the EV. `RiskManager::PrintBrokerProfile()` now prints
the whole spec at init.

## How to capture it

Attach the EA once; the Experts log prints a block like:

```
# --- detected broker profile (parse with research/broker_profile.py) ---
symbol=XAUUSD
contract_size=100.0000
min_lot=0.0100
lot_step=0.0100
max_lot=100.0000
tick_size=0.01000000
tick_value=1.00000000
point=0.01000000
digits=2
spread_points=30.0
stops_level_points=0
commission_per_lot=0.000000
account_equity=10000.00
account_currency=USD
```

Copy it to a file, e.g. `research/broker.txt`. Note `spread_points` is the
CURRENT spread - sample it across London/NY/Asia for a real average, since the
average is what the EV should use. If `commission_per_lot` is 0 (no history
yet), set it from your broker's contract specification.

## How the EV uses it

```python
from broker_profile import BrokerProfile
bp = BrokerProfile.from_mt5_kv(open("broker.txt").read())
print(bp.summary())
bp.breakeven_win(tp=0.5, sl=1.0)   # win rate needed after the DETECTED cost
bp.can_trade(stop_price=6.0, risk_pct=1.0)   # is min lot even affordable?
bp.lots_for_risk(stop_price=6.0, risk_pct=1.0)
```

And directly from the CLI:

```
python3 research/scalp_ev.py --broker research/broker.txt --tp 0.5 --sl 1.0 --win 0.93
```

The `--broker` flag replaces the assumed spread with the detected round-trip
cost, so the break-even win rate reflects the real broker rather than a guess.

## Why this matters

Break-even for a scalp is `p* = (SL + s) / (TP + SL)` where `s` is the real
round-trip cost. A wide-spread broker can move `p*` from 80% to above 100% - the
same rule that is profitable on one broker is unwinnable on another. Detecting
`s` (and the contract spec) means the same EV works anywhere, and tells you
up front whether a mechanism is viable on the account it will actually run on.

It also answers the small-account question generically: `can_trade()` reports
whether one minimum lot at the intended stop fits inside the risk budget, for
any contract size.
