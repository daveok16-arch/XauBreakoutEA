# Importing a Deriv / MT5 CSV

The long-history H1/H4 experiment needs more H1 history than the free feed
provides. Export it from Deriv MT5 and load it with the dedicated loader.

## Export from Deriv MT5

1. Open MT5, Tools -> Options -> Charts, and set "Max bars in chart" to
   Unlimited.
2. Open a XAUUSD H1 chart and scroll back as far as it will go (this forces the
   terminal to download history).
3. Tools -> Options -> Charts, or File -> Open Data Folder -> `bases/`, and find
   `XAUUSD/H1.hc`. Easiest route: use a script or the "Export" in the Symbols
   window; either way produce a CSV with a datetime and OHLC columns.
4. Keep the raw file untouched. The loader reads it and writes a *separate*
   normalised copy.

## Load and validate

```bash
# report only (no writes)
python3 research/fetch_data.py --csv ~/XAUUSD_H1.csv

# writes a normalised copy to research/data/GC_F_h1.csv, raw file untouched
python3 research/fetch_data.py --csv ~/XAUUSD_H1.csv --name h1

# if your broker server time is not UTC, shift it and note that you did
python3 research/fetch_data.py --csv ~/XAUUSD_H1.csv --shift-hours 2
```

Accepted shapes: comma/semicolon/tab delimiters; a single datetime column or
separate Date + Time; Open/High/Low/Close plus optional volume under
`Volume`, `TickVolume`, `RealVolume`, or `<TICKVOL>`/`<VOL>`; broker-prefixed
headers such as `XAUUSD_Open`.

The report covers: rows in file, malformed rows, duplicates removed, OHLC
inconsistencies, nonpositive prices, rows kept, date range, inferred timeframe,
the timestamp column used, the timezone convention, and every interior gap
(flagged, never filled).

## Timezone convention

MT5 exports broker *server* time with no offset. The loader treats the raw wall
clock as UTC and records that explicitly. It never guesses. If your server is
not UTC, `--shift-hours` aligns it, and the shift is printed in the report -
because it moves session boundaries and therefore changes which bars fall in
which session.

## The validation gate

```bash
python3 research/validate_import.py --csv ~/XAUUSD_H1.csv
```

Two checks:

1. **Self-consistency** (always runs). Serialises the known-good cached series
   to a broker-style CSV, pushes it back through the loader, and requires
   identical timestamps, OHLC, and trade sequence. This is the check that
   proves the normalisation pipeline is sound. It currently passes: 13,732
   timestamps, identical OHLC, loader idempotent, **439/439 trades identical**.

2. **Overlap** (when `--csv` is given). Compares the import against the existing
   series over their common window.

## Important caveat: futures proxy vs broker spot

The existing cache is **COMEX gold futures (GC=F)**, the best free proxy for
XAUUSD. A Deriv export is **spot XAUUSD**. They are different instruments with a
basis between them, so an exact OHLC match over the overlap is impossible by
construction.

The gate handles this honestly:

- If the overlap close prices match >99.9%, it treats them as the same
  instrument and applies the strict rule: identical trade sequence or **STOP**.
- If they do not, it reports the divergence, scans for a timezone/session shift
  (a nonzero shift that fits much better means a bug - **STOP**), and otherwise
  returns **INCONCLUSIVE**, refusing to claim a pass.

So with a real Deriv export the strict gate cannot certify the import. The
self-consistency gate is what certifies the *pipeline*; the overlap gate will
say INCONCLUSIVE for a different instrument, and that is the correct answer.

## Running the long-history study

```bash
python3 research/long_history.py --csv ~/XAUUSD_H1.csv --folds 8
```

Runs the five pre-registered steps: H1 only, H4 only, H1+H4 independent,
H1+H4 shared, and the OOS/regime breakdown. **H4 parameters are fixed at the
harness defaults and are not tuned against the imported history** - the point is
to validate an existing hypothesis, not to search for one.

The harness ends with an explicit production gate. It grants permission to wire
the combined system into `Experts/` (default-off) only if:

- the shared variant beats H1-only on CAGR without adding drawdown, and
- it is positive in at least 75% of out-of-sample segments, and
- there is at least **8 years** of history covering **at least 2 regimes**.

The last two conditions exist because a short, single-regime window can pass the
performance test by luck. On the 2.4-year free series the gate correctly blocks
with "2.4 years < 8.0 required".

## Instrument comparison (diagnostic only)

```bash
python3 research/compare_instruments.py --csv ~/XAUUSD_H1.csv
```

Spot XAUUSD and COMEX GC do not need identical prices for breakout research to
transfer. What matters is whether their breakouts, volatility, ATR behaviour and
resulting signals are similar. This tool separates three things:

**A. Price-level basis** (informative, not decisive): basis in absolute and % of
the reference, mean/median/std, P5/P95, max, drift by quartile, and basis by
hour of day (session structure).

**B. Return / structure equivalence**: price correlation *and* return
correlation, return-sign agreement, bar-direction agreement.

**C. Donchian signal equivalence**: runs the same breakout logic on both series
and reports signal counts, Jaccard overlap, entry-direction agreement, signal
timestamp displacement, ATR ratio, stop-distance ratio, and trade-level
agreement.

A worked example, using a synthetic "spot" (1.8 basis + small noise):

```
RETURN correlation       : 0.9998   (price corr 1.0000)
bar direction agreement  : 98.2%
breakout Jaccard overlap : 96.6%
entry-direction agreement: 100.0%
signal displacement      : median 0.0h
ATR ratio                : mean 1.001
-> structure and signals look equivalent; the futures baseline is probably usable
```

And the failure mode it is designed to catch - a 2-hour session mismatch:

```
price correlation        : 0.9998   <- looks fine
RETURN correlation       : 0.0746   <- the one that matters
breakout Jaccard overlap : 11.9%
signal displacement      : median 2.0h
-> material structural differences. Do NOT use the futures baseline.
```

That contrast is the whole point: **price correlation of 99.98% can coexist with
a completely broken structural relationship.**

### Gate isolation

`--compare-instrument` is strictly diagnostic. It **explains** an INCONCLUSIVE
result; it can never turn INCONCLUSIVE into PASS. `validate_import.py` does not
import or consult `compare_instruments.py`, and a test asserts this so the
isolation cannot regress.

## Preflight (run this first)

```bash
python3 research/preflight.py --csv ~/XAUUSD_H1.csv
```

Cheap, read-only, and it decides whether the expensive experiment is worth
running. It checks and prints:

```
=== preflight ===
  [ok] date range                                 : 2024-05-10 04:00:00 .. 2026-10-02 20:00:00
  [ok] row count                                  : 13732 bars
  [ok] inferred timeframe = H1                    : H1
  [ok] duplicate count = 0                        : 0 duplicates
  [ok] no malformed rows                          : 0 malformed
  [ok] no inconsistent OHLC                       : 0 inconsistent
  [!!] history >= 8 years                         : 2.4 years
  [ok] bar density plausible (>=80% of expected)  : 96% of ~14,375 expected

  earliest timestamp (authority) : 2024-05-10 04:00:00
  gaps flagged                   : 21  (1-7 days: 4  1-2 bars: 15  3-24 bars: 1)

  PREFLIGHT: BLOCKED - history >= 8 years
    history is 2.4 years, 5.6 short of the 8-year gate.
    Check the broker's server history, not just 'Max bars in chart'.
    Do NOT run the long-history experiment on this file.
```

Exit code 0 = clear to run the experiment; 1 = do not run it.

### Why the earliest timestamp is the authority

Setting "Max bars in chart" to Unlimited is necessary but **not sufficient** for
historical completeness. If the broker's server history itself does not extend
far enough, the CSV can be perfectly valid - right timeframe, no duplicates, no
malformed rows - and still far too short for the research gate. A valid file is
not the same as a sufficient file. The earliest timestamp actually present is
the authority, and the preflight compares it to the required minimum rather than
trusting that the export "should" be long enough.

The bar-density check catches the mirror case: a long date range that is
sparsely populated (for example, only recent months present but a stray old bar
setting the start date). Density is measured against ~115 H1 bars/week, the
approximate gold trading week.

## The clean sequence

```
preflight -> import -> validate -> instrument comparison -> 8+ year H1/H4 experiment
          -> OOS/regime gate -> only then consider touching Experts/
```

The preflight is the gate on the gate: it stops a too-short file before it
consumes the experiment. `--compare-instrument` sits between validate and the
long-history experiment. It tells you how to *read* the long-history numbers; it
does not authorise anything on its own.

## Tests

```bash
python3 -m unittest discover -s research/tests -p "test_*.py" -v
```

35 tests: three loader fixtures plus fetcher paging, dedup, epoch conversion, gate isolation and preflight exit codes. 27 cover the (MT5 tab-delimited with a gap, semicolon with
prefixed headers, and a dirty file with a duplicate, a malformed row, an
inconsistent row and a nonpositive price).

## Alternative source: the Deriv API

Better than an MT5 CSV export for this project, because it removes two problems
at once: it is the actual traded instrument (so the spot-vs-futures
INCONCLUSIVE largely disappears) and it returns true-UTC epochs (so there is no
broker-server-time guesswork and no `--shift-hours`).

Market data on Deriv is **no-auth**. `ticks_history`, `active_symbols` and
candles need no API token. An app_id only identifies the application and the
public default `1089` works for data. Do not pass an API token to this tool - it
is not needed, and a token can place trades.

```bash
# 1. DECISION POINT: how far back does Deriv's gold H1 actually go?
python3 research/deriv_fetch.py --probe --symbol frxXAUUSD
#    exit 0 = reaches the 8-year gate; exit 1 = too short

# 2. only if the probe clears:
python3 research/deriv_fetch.py --fetch --symbol frxXAUUSD --out research/data/deriv_XAUUSD_H1_raw.csv

# 3. then the existing pipeline, unchanged:
python3 research/preflight.py           --csv research/data/deriv_XAUUSD_H1_raw.csv
python3 research/validate_import.py     --csv research/data/deriv_XAUUSD_H1_raw.csv
python3 research/compare_instruments.py --csv research/data/deriv_XAUUSD_H1_raw.csv
python3 research/long_history.py        --csv research/data/deriv_XAUUSD_H1_raw.csv --folds 8
```

The probe pages backwards until history is exhausted and prints the earliest
available candle. Depth is the open question - the API has a per-request `count`
cap, so the fetcher pages with `end` stepping back one granularity at a time and
dedups by epoch. If the probe shows Deriv's gold history is short, the answer is
Deriv for execution realism plus a deep-history source (Dukascopy) for the long
record, reconciled with `compare_instruments.py`.

If the connection returns a Cloudflare 520, that is network egress, not a
credential problem: run it from a host that can reach the Deriv websocket.

The fetcher's paging, dedup and epoch-conversion logic is covered by tests using
a fake client, so only the live connection is left to confirm.
