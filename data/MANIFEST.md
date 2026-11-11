# Data manifest

Raw files stay out of git (Coinbase's terms forbid redistributing them). This file lets a stranger record the same
kind of data and check that a copy of mine is unchanged.

**Status: capture running.** Rows marked *pending* are filled from `make manifest` when it ends.

| field | value |
|---|---|
| Source | Coinbase Exchange public websocket feed, `wss://ws-feed.exchange.coinbase.com` ("Coinbase Market Data", no authentication) |
| Channel | `level2_batch`. Checked 2026-11-10 in the Exchange WebSocket docs: batches of level2 messages every 50 ms, same schema as `level2`, no authentication; `time` is that of the most recent message in the batch. `level2` itself needs authentication. |
| Product | BTC-USD |
| Tick size | 0.01 USD. `GET https://api.exchange.coinbase.com/products/BTC-USD` on 2026-11-10: `quote_increment "0.01"`, `base_increment "0.00000001"` |
| Units in Parquet | all Int64: `ts_ns` exchange time (ns), `recv_ns` local receive time (ns), `bid_tick`/`ask_tick` (0.01 USD), `bid_sz`/`ask_sz` (satoshi, 1e-8 BTC) |
| Capture start (UTC) | process started 2026-11-10T08:25:22Z; first receive *pending* |
| Capture end (UTC) | planned 2026-11-14 about 12:00 (`--hours 99.5`); stops early if free disk drops below 1 GB; actual *pending* |
| Period vs theirs | Theirs: "three days", dates and hours not stated. Mine: about 4.1 days, Tuesday to Saturday midday, every hour of the day, four weekdays plus half of a Saturday. Theirs could be any three days, so the two periods are assumed not to overlap (definitions A2). |
| Machine, location, network | Apple M1 MacBook, macOS 27.0.1, home broadband (location: *Timothy to fill in*). Receive times are this machine's clock; nothing in the result uses them. |
| Tool and version | capture: `scripts/capture.py` at commit `02c8bde` (Python 3.13.5, websockets 17.4). Replay and manifest: commit *pending* (the one that writes this file's measured rows). |
| Reconnects | *pending* (every one is listed below with its reason) |
| Replay stats | *pending* (lines, snapshots, updates, rows, skipped_invalid, bad_lines, truncated_files) |
| Gaps over 1 s | *pending* (every one is listed below) |
| Licence and terms | Coinbase Market Data Terms of Use, last updated 2026-08-07, read 2026-11-10: use is limited to personal or research purposes, and without Coinbase's written consent you may not redistribute the data **or display works derived from it** to third parties. The raw files are not in this repo. Whether the derived numbers may be published needs settling before the report goes public. |

## Files

*pending*: paste the output of `make manifest` here.
