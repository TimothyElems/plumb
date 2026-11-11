# Their definitions, and what I used

Committed before any real data was recorded or any number was computed.

**Source.** HFT Architecture, "A worked case: on Coinbase BTC-USD the spread is one tick more than half the time",
on <https://hftarchitecture.com/consulting>. Read twice on 2026-11-09. The page carries no publication date.
A local reference copy of the section's text is kept out of git (it is their writing, not mine to redistribute);
its sha256 is `cd29ca5b852d9ebb5a1618a7b5c80981bd3711c31d96ecd93de52f278814c375`, so a later edit to their page can be detected.

Quotes below are their exact words, kept short. Anything they do not say is marked **unknown**.
Every value I chose to fill an unknown is marked **ASSUMPTION** with a number, so the report can refer to it.

## Worksheet

| Item | Their wording or value (exact) | What I will use | Assumption? |
|---|---|---|---|
| What is a "state" | "book states" (never defined). **unknown** | One state = the top of book after applying one `l2update` message. On `level2_batch` that is one state per 50 ms batch, not per exchange event. | **A1** |
| Period and length | "three days". Dates, hours and weekday/weekend mix: **unknown** | My own capture, at least 24 h, a weekday plus part of a weekend. Exact UTC start and end in `data/MANIFEST.md`. | **A2** (period cannot match theirs) |
| Sampling clock | **unknown**. Their headline unit is "% of book states", which counts states, not time | Primary: per state (per batch), every state weighted equally. Also reported: time-weighted, and a 1 s grid. | **A3** |
| Tick size | "The tick is $0.01." | 0.01 USD. Confirmed 2026-11-09 from `GET https://api.exchange.coinbase.com/products/BTC-USD`: `"quote_increment": "0.01"`. Prices are converted to integer ticks through `Decimal`, never compared as floats. | No (stated, and checked) |
| Spread definition | "the spread", with bins starting at "exactly 1 tick". Formula: **unknown** | best ask tick − best bid tick, an integer. "One tick" means exactly 1. | **A4** (the usual definition, but they do not write it) |
| Depth 5 | "reconstructed to depth five". What that means (top 5 levels kept from a full book, or a book rebuilt from 5-level data): **unknown** | A full-depth book rebuilt from the `level2_batch` snapshot plus every update. The spread only needs level 1. A depth-5 truncation is a later variant (Block 4), not the baseline. | **A5** |
| Locked and crossed books | **unknown**. Not mentioned. Their bins start at 1 tick and add to 100.01%, so locked/crossed states were either absent or left out | Excluded from the denominator, and both counts reported. Variant: kept. | **A6** |
| Data source, channel, time field | "Coinbase BTC-USD", "Public exchange data". Channel and time field: **unknown** | Coinbase Exchange websocket `wss://ws-feed.exchange.coinbase.com`, channel `level2_batch` (public; `level2` needs authentication). Time = the exchange `time` field of each `l2update`, as integer ns (`ts_ns`). Receive time kept as `recv_ns`. | **A7** |
| Feed gaps | "Reconstruction gaps cover about 13 seconds of one day" | Every gap over 1 s and every reconnect listed in the manifest. No states are written between a reconnect and the next snapshot. Time-weighting caps any one state at 10 s. | **A8** (the 1 s and 10 s thresholds are mine) |

## Their numbers, as published

| Spread | Share of book states |
|---|---|
| exactly 1 tick | 55.60% |
| 2–3 ticks | 1.62% |
| 4–20 ticks | 3.93% |
| 21–100 ticks | 16.15% |
| 101–500 ticks | 20.90% |
| over 500 ticks | 1.81% |

Also stated: 29,263,059 book states; p75 = 83 ticks, p90 = 205, p99 = 633.
They name the main limit themselves: the result may be "what a depth-five reconstruction makes of it."

## What their own numbers imply (my arithmetic, not their words)

- 29,263,059 states over three days is about **113 states per second**. A 50 ms batch feed gives at most 20 per second
  (5,184,000 in three days). So their "state" is almost certainly finer than a `level2_batch` batch, probably one per
  exchange event. A1 is a known difference before I record anything.
- The bins add to 100.01%, which is rounding. There is no bin for 0 or fewer ticks.

## Counting rule closest to their wording

**Per state (per batch), equal weight.** They report a share "of book states", which counts states one by one, not time or grid points.
