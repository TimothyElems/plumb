# Why we differ

The table with numbers is kept off this repo: it is derived from Coinbase data (see README). This file fixes the
method, so anyone with their own recording can produce the same table:

```
python -m plumb.differ data/raw/*.tsv.gz --out docs/local/why_we_differ.md
```

## Baseline (fixed, never changed while the table is built)

The definition in `docs/match-rule.md`: one state per `level2_batch` update, equal weight; full-depth book; locked and
crossed books dropped; exchange `time`; the whole capture; durations capped at 10 s.

## Factors, each changed alone

| Factor | Variant | How it is run |
|---|---|---|
| State definition | a state after every change inside a batch | replay with `per_change=True`, streamed (about 100 million states on the full capture) |
| Depth-5 construction | the book only ever knows 5 levels a side; changes outside them are discarded | replay with `Book(depth=5)` |
| Counting rule | time-weighted; 1 s grid | `spread.share_time_weighted`, `spread.share_on_grid` |
| Locked and crossed books | kept in the denominator | `locked="keep"` |
| Timestamp field | receive time instead of exchange time | `time="recv"` |
| Period length | first 72 h only, their length | `max_hours=72` |
| Tick size and rounding | floor instead of round | not re-run: every price string is checked against the 0.01 grid. If none is off it, floor and round cannot differ |
| Gap and stale-book handling | no cap on durations | cannot move a per-state share; it moves the time-weighted share only |
| Feed and channel | unbatched `level2` | **not testable**: needs authentication. Stays on the unexplained list |

Rows are sorted by the size of the change. Then the two largest are changed together. If that pair is undefined (a
per-change state has no duration of its own, so it cannot be combined with a time clock), the file says so and also
gives the next largest pair that is defined. Whatever gap remains is listed as unexplained. No reason is invented to close it.

## Depth on its own

Depth must not move the spread: changes below the top five levels can never change best bid or best ask.
`tests/test_replay.py::test_updates_below_the_top_never_move_the_spread` applies 5,000 random changes at levels 6 and
deeper and checks this. A depth-*limited* reconstruction is different: it discards levels it never kept, so when the
top empties it cannot know the true next level. That is a factor in the table, not a bug.

## Checks made on the method itself

- Combining "state definition" with "depth 5" first returned exactly the per-change number. The per-change replay
  ignored the depth setting. Found on a dry run, fixed under `tests/test_differ.py::test_per_change_respects_depth`.
- A test meant to cover the order-book heaps did not: a deliberately broken `best()` passed it. A second test that also
  removes top levels catches that mutant.
