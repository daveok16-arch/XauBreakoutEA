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

## Tests

```bash
python3 -m unittest discover -s research/tests -p "test_*.py" -v
```

16 tests over three fixtures (MT5 tab-delimited with a gap, semicolon with
prefixed headers, and a dirty file with a duplicate, a malformed row, an
inconsistent row and a nonpositive price).
