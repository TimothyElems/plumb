# Match rule

Written 2026-11-09, before any real data was recorded. Do not edit after a number is seen.
Its commit is the first commit that touches this file: `git log --follow -- docs/match-rule.md`.
Any later commit to this file is a breach of the rule, and the report must say so.

## The number I compare

The share of book states whose spread is exactly 1 tick, measured with:

- **Counting rule:** per state (one state per `level2_batch` update message), equal weight. (definitions A1, A3)
- **Book:** full depth, rebuilt from the snapshot plus every update. (A5)
- **Locked and crossed:** dropped from the denominator, counts reported. (A6)
- **Time:** exchange `time` field. (A7)
- **Period:** the whole of my capture, every hour kept. (A2)

## The rule

1. I compute a 95% moving-block bootstrap interval for that share, block length 1,000 states, 2,000 resamples, seed 7.
2. **Match** if 55.60% lies inside that interval. **No match** otherwise.
3. Block lengths 100 and 10,000 are reported too, but only block 1,000 decides the verdict.
   If the verdict changes with block length, the report says so in its first paragraph.
4. The time-weighted and 1 s grid shares are reported beside it. They never decide the verdict.
5. Whatever the verdict, the report gives the gap in percentage points (mine minus 55.60) and states the clock, period and book rule used.

## What a match would and would not mean

A match means my data cannot rule out their number. It does not mean our data agree, since the period, the state
definition and the reconstruction depth all differ (definitions A1, A2, A5).
A no-match means their number does not describe this book under these definitions. It does not mean they are wrong.

## Expectation, written before data

From their own count (113 states per second, against at most 20 batches per second) and the depth-five caveat they
publish, I expect my per-batch, full-depth share to differ from 55.60% by more than the interval width.
I write this down so it cannot be adjusted after the fact. The rule above decides; this sentence does not.
