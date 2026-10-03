# Running XauBreakoutEA on Deriv MT5

Deriv is not a generic forex broker, and a few of its specifics change how this
EA must be configured. Read this before attaching it to a live chart.

## 1. Use the right account

Deriv exposes several MT5 account types. They are **not** interchangeable:

| Account | Contains XAUUSD? | Use it? |
|---|---|---|
| **Gold** | Yes - gold + metals only | **Best choice** for this EA |
| **Financial** | Yes - forex, metals, indices, crypto | Works |
| **Standard (CFD/Derived)** | Synthetics (Volatility, Boom/Crash, Jump) | **No** - no real XAUUSD |
| **Zero Spread** | Yes, 0 spread + commission | Fine, but set commission in backtests |

The "Derived Indices" (Volatility 75, Boom/Crash, etc.) are Deriv's own
24/7 synthetic instruments. They are **not** XAUUSD. The EA's breakout logic
was validated on gold; running it on synthetics is untested and the session /
news filters are meaningless there.

## 2. Confirm the symbol before trading

Attach the EA to the exact gold symbol in your Market Watch - it may be
`XAUUSD`, `XAUUSD.raw`, or similar. Then check the **Experts** log on startup.
The EA prints a symbol report and refuses to start if the contract is unusable:

```
XauBreakoutEA symbol check: XAUUSD contract=100.0 digits=2 point=0.01
  ticksize=0.01 tickvalue=1.00000 pointvalue/lot=1.00000 bid=4155.20
```

Key rows to verify in Market Watch -> right-click symbol -> **Specification**:

- **Contract size** - usually `100` (100 oz per lot). Deriv micro accounts may
  show `10` or `1`. The EA sizes from tick value, so it stays correct, but a
  non-100 contract gets a warning in the log.
- **Tick value / Tick size** - must be non-zero, otherwise the EA aborts.
- **Volume step** - `0.01` lets the risk sizing land accurately. If Deriv uses
  `0.1`, the minimum position may be larger than 0.75% risk on a small account.

## 3. The minimum-lot trap (small accounts)

XAUUSD is priced in the thousands, so one lot is a big position. With
`contract=100`, a 0.01 lot already moves $1 per $1 of gold price.

At risk = 0.75% of equity with a stop of 1.5 x ATR, the EA may compute a size
**below** the minimum lot. `NormalizeLots` clamps up to the minimum, which
means the real risk is higher than requested. On a small account this matters:

- On a $1,000 account, 0.75% = $7.50 risk. If ATR(14) is ~$20, the stop is
  ~$30 away, and 0.01 lot risks ~$30 - i.e. ~3%, not 0.75%.
- **Check the log line** and, if needed, lower `InpStopAtrMult` or accept a
  larger effective risk, or fund the account so the minimum lot fits the risk.

This is the single most likely way to get hurt on Deriv. Verify it on demo.

## 4. Server time is not your local time

Our inputs are expressed in **server hours**:

- `InpSessionStartHour` / `InpSessionEndHour` - default 7-20.
- `InpFridayStopHour` - default 20.

There is conflicting public information about Deriv's server offset (some
sources say GMT+0, others the common GMT+2/+3 forex convention). Do not trust
either - **measure it**: compare the time in Market Watch (Ctrl+M) against a
known UTC clock, or check a tick from a news release with a published UTC time.

The default 7-20 window covers the London/NY overlap (roughly 12:00-16:00 UTC)
under most offsets. Tighten it once you know your server's offset.

## 5. Costs: Deriv charges no commission

Deriv advertises zero commission on MT5. That makes the EA's economics
**better** than the research assumed. The Python harness modelled
`spread 0.30 + commission 0.07/side`; on Deriv you can drop the commission and
use the live gold spread instead. Measured on the daily series:

| Cost model | Return | PF | Max DD |
|---|---|---|---|
| generic ECN (0.30 + 0.07/side) | 53.1% | 1.53 | 12.5% |
| **Deriv zero-commission (0.30 + 0)** | **57.0%** | **1.55** | **12.1%** |
| Deriv zero-comm, tight spread (0.15) | 62.5% | 1.58 | 11.7% |
| Deriv zero-comm, wide spread (0.60) | 46.0% | 1.48 | 13.4% |

The edge survives even a 0.60 spread, so the no-commission model is a real
tailwind rather than something the strategy depends on.

- Deriv periodically runs "spread advantage hours" that cut XAUUSD spread by up
  to 50%. The EA already has `InpMaxSpreadPoints` to skip bad fills.

## 6. Hedging vs netting

Deriv MT5 supports **multiple positions per symbol and simultaneous buy/sell**
(hedging). The EA opens at most `InpMaxPositions` positions, so it behaves the
same either way - but if you ever change it to scale in, remember Deriv's
hedging model means each entry is its own ticket.

## 7. Install

1. In MetaEditor, open the Deriv data folder (File -> Open Data Folder).
2. Copy `Include/RiskManager.mqh` and `Include/NewsGuard.mqh` -> `MQL5/Include/`.
3. Copy `Experts/XauBreakoutEA/` -> `MQL5/Experts/XauBreakoutEA/`.
4. Compile with F7 (no errors expected).
5. Drag onto an XAUUSD chart, enable **Algo Trading**, and read the Experts log.

## 8. Backtesting on Deriv data

- Use **Every tick based on real ticks**. Deriv's synthetic indices are
  server-generated and perfectly tick-accurate; real XAUUSD quality depends on
  the feed, so sanity-check the model quality percentage in the tester.
- Set the tester's symbol and period to match live (XAUUSD, chart timeframe
  irrelevant to the EA - it reads its own ATR on the chart TF).
- Confirm spread in the tester matches live; Deriv's no-commission model means
  spread is the only cost to model.

## 9. Recommended first run

1. Deriv **demo** Gold account, $1,000+.
2. Attach with defaults, Algo Trading on, and let it run 4+ weeks.
3. Read the Experts log for the symbol-check line and any rejected orders.
4. Only after forward-testing, move to a small live balance and start at the
   smallest risk that respects the minimum lot.
