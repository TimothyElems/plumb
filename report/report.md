# Plumb: BTC-USD spread, tested

**Result:** I measured the share of Coinbase BTC-USD book states with a one-tick spread on my own recording, and compared it
with the 55.60% in HFT Architecture's worked case under a match rule committed before any data. The number, its intervals,
the gap and the verdict are kept off this public copy: Coinbase's Market Data Terms do not allow showing works derived from
their data to third parties without consent. The full report is generated locally (`report/local/report.md`) by
`scripts/write_report.py`, and anyone can produce their own with the steps under Rerun.

## Definitions
Their wording, my values, each assumption marked A1–A8: docs/definitions.md. Match rule, fixed in advance: docs/match-rule.md.
The two that matter most: their 29,263,059 "book states" over three days are about 113 a second, while my 50 ms batches
are at most 20 a second (A1); their book was "reconstructed to depth five", mine is full depth (A5).

## Data
Coinbase Exchange websocket, `level2_batch`, BTC-USD, recorded by me, about 4 days in November 2026. Source, period,
tool versions, hashes, reconnects and gaps: data/MANIFEST.md. Raw files are not redistributed.

## Method
Spread in integer ticks (prices parsed with `Decimal`). Three counting rules: per state (the verdict), time-weighted
(each state capped at 10 s) and a 1 s grid (skipping locked, crossed and stale states). Locked and crossed books are
dropped from the denominator and counted. Moving-block bootstrap at block lengths 100, 1,000 (the verdict) and 10,000;
the report says plainly if the interval grows with block length. Share by hour of day with its own interval.
Ten states hand-checked against an independent replay: docs/hand-check.md.

## Why we differ
One fixed baseline, each factor alone, sorted by size, then the two largest together: docs/why_we_differ.md.

## Limits
- One venue (Coinbase Exchange) and one product (BTC-USD).
- My own recording period, not theirs. Their dates are not published.
- One clock family: states, time and a grid, all from the same batched book.
- A batched feed: `level2_batch` groups updates every 50 ms, so a state is a batch, not an exchange event.
- I never saw their data or their code. Everything about their method comes from one published page.

## Rerun
```
make capture HOURS=96 && make replay && make result
python -m plumb.differ data/raw/*.tsv.gz
python scripts/plot_hourly.py data/book.parquet
python scripts/write_report.py
```
