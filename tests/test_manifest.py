import gzip
import hashlib
import json

from plumb.replay import replay_files
from scripts_manifest import build_manifest

S = 1_000_000_000
T0 = 1_794_268_800 * S  # 2026-11-10T00:00:00Z


def iso(ns):
    import time
    sec, frac = divmod(ns, S)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + f".{frac:09d}"[:8] + "Z"


def upd(ns):
    return {"type": "l2update", "product_id": "BTC-USD", "time": iso(ns), "changes": [["buy", "100.00", "1"]]}


SNAP = {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "1"]], "asks": [["100.01", "1"]]}


def test_manifest_lists_hashes_window_rows_reconnects_and_gaps(tmp_path):
    raw = tmp_path / "btcusd_level2_batch_20261110T00.tsv.gz"
    msgs = [(T0, SNAP), (T0 + S // 20, upd(T0 + S // 20)), (T0 + S // 10, upd(T0 + S // 10)),
            # 3.4 s hole in the feed, no reconnect
            (T0 + 35 * S // 10, upd(T0 + 35 * S // 10)),
            (T0 + 4 * S, {"type": "plumb_reconnect", "reason": "ConnectionClosedError: no close frame"}),
            (T0 + 6 * S, SNAP), (T0 + 6 * S + 1, upd(T0 + 6 * S))]
    with gzip.open(raw, "wt") as f:
        for ns, m in msgs:
            f.write(f"{ns}\t{json.dumps(m)}\n")
    df, _ = replay_files([raw])
    pq = tmp_path / "book.parquet"
    df.write_parquet(pq)

    md = build_manifest([raw], pq)
    assert hashlib.sha256(raw.read_bytes()).hexdigest() in md
    assert "| Rows | 4 |" in md
    assert "2026-11-10T00:00:00" in md and "2026-11-10T00:00:06" in md  # receive window
    assert "ConnectionClosedError: no close frame" in md and "| Reconnects | 1 |" in md
    assert "| Gaps over 1 s | 2 |" in md  # the 3.4 s hole, and the 2.5 s hole around the reconnect
    assert "3.400" in md and "2.500" in md
