import asyncio
import gzip
import json

import polars as pl
import websockets

from plumb.replay import Book, parse_time_ns, replay_files, replay_lines


def L(recv, msg):
    return f"{recv}\t{json.dumps(msg)}\n"


SNAP = {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "1"], ["99.99", "2"]], "asks": [["100.01", "1"], ["100.03", "3"]]}


def test_snapshot_then_update_gives_expected_top_of_book():
    lines = [L(1, SNAP),
             L(2, {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["sell", "100.01", "0"]]}),
             L(3, {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000002Z", "changes": [["buy", "100.02", "0.5"]]})]
    rows = [r for r in replay_lines(lines) if "__stats__" not in r]
    assert (rows[0]["bid_tick"], rows[0]["ask_tick"]) == (10000, 10003)  # best ask moved to 100.03
    assert (rows[1]["bid_tick"], rows[1]["ask_tick"]) == (10002, 10003)  # new best bid 100.02


def test_size_is_total_not_delta_and_zero_removes():
    b = Book()
    b.snapshot([["100.00", "1"]], [["100.01", "1"]])
    b.update([["buy", "100.00", "5"]])
    assert b.best()[1] == 5 * 10**8  # 5 BTC, in satoshi
    b.update([["buy", "100.00", "0"], ["buy", "99.99", "2"]])
    assert b.best()[0] == 9999


def test_reconnect_invalidates_until_next_snapshot():
    upd = {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "2"]]}
    lines = [L(1, SNAP), L(2, upd), L(3, {"type": "plumb_reconnect"}), L(4, upd), L(5, SNAP), L(6, upd)]
    out = list(replay_lines(lines))
    rows, stats = [r for r in out if "__stats__" not in r], out[-1]["__stats__"]
    assert len(rows) == 2 and stats["skipped_invalid"] == 1 and stats["reconnects"] == 1


def test_bad_lines_are_counted():
    out = list(replay_lines(["garbage\n", L(1, SNAP)]))
    assert out[-1]["__stats__"]["bad_lines"] == 1


def test_time_parse_is_exact():
    assert parse_time_ns("1970-01-01T00:00:01.000002Z") == 1_000_002_000


def test_replay_files_reads_gzip(tmp_path):
    p = tmp_path / "x.tsv.gz"
    with gzip.open(p, "wt") as f:
        f.write(L(1, SNAP))
        f.write(L(2, {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["sell", "100.01", "0"]]}))
    df, stats = replay_files([p])
    assert df.height == 1 and df["ask_tick"][0] == 10003 and stats["snapshots"] == 1
    assert df.schema["bid_tick"] == pl.Int64


def test_capture_writes_raw_lines_and_marks_reconnect(tmp_path):
    from scripts_capture import run  # loaded by conftest from scripts/capture.py

    async def handler(ws):
        sub = json.loads(await ws.recv())
        assert sub["channels"] == ["level2_batch"] and sub["product_ids"] == ["BTC-USD"]
        await ws.send(json.dumps(SNAP))
        await ws.send(json.dumps({"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "2"]]}))
        await ws.close()  # force a reconnect

    async def main():
        async with websockets.serve(handler, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            return await run(f"ws://127.0.0.1:{port}", "BTC-USD", "level2_batch", tmp_path, seconds=3.0, stem="t")

    stats = asyncio.run(main())
    assert stats["messages"] >= 2 and stats["reconnects"] >= 1
    df, rstats = replay_files(sorted(tmp_path.glob("t_*.tsv.gz")))
    assert rstats["reconnects"] >= 1 and df.height >= 1


def test_time_parse_keeps_every_fractional_digit():
    # Real messages carry 6 digits ("2026-11-10T08:23:31.944193Z"). Finer times must not be cut silently.
    assert parse_time_ns("1970-01-01T00:00:01.0000021Z") == 1_000_002_100
    assert parse_time_ns("2026-11-10T08:23:31.944193Z") % 1_000_000_000 == 944_193_000
    assert parse_time_ns("1970-01-01T00:00:01Z") == 1_000_000_000


def test_parquet_columns_are_all_integers_and_sizes_exact():
    lines = [L(1, {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "0.12345678"]], "asks": [["100.01", "1.00000001"]]}),
             L(2, {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "0.30000000"]]})]
    rows = [r for r in replay_lines(lines) if "__stats__" not in r]
    assert rows[0]["bid_sz"] == 30_000_000 and rows[0]["ask_sz"] == 100_000_001  # satoshi, no float
    assert all(isinstance(v, int) for v in rows[0].values())


def test_replay_files_schema_is_int64(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text(L(1, SNAP) + L(2, {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["sell", "100.01", "0"]]}))
    df, _ = replay_files([p])
    assert set(df.schema.values()) == {pl.Int64}, df.schema


def test_truncated_gzip_is_replayed_up_to_the_cut(tmp_path):
    # A capture killed mid-hour leaves a gzip file with no end marker. Raw files are never repaired,
    # so the replay must read what is there, count the file, and carry on.
    upd = {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "2"]]}
    body = gzip.compress(("".join([L(1, SNAP)] + [L(2 + i, upd) for i in range(2000)])).encode())
    cut = tmp_path / "a.tsv.gz"
    cut.write_bytes(body[: len(body) - 40])
    whole = tmp_path / "b.tsv.gz"
    whole.write_bytes(body)
    df, stats = replay_files([cut, whole])
    assert stats["truncated_files"] == 1
    assert 2000 < df.height < 4000


def test_book_carries_across_hourly_files(tmp_path):
    # The capture rolls to a new file every hour; the snapshot is only in the first one.
    upd = {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "2"]]}
    (tmp_path / "x_20261110T08.tsv").write_text(L(1, SNAP) + L(2, upd))
    (tmp_path / "x_20261110T09.tsv").write_text(L(3, upd) + L(4, upd))
    df, stats = replay_files(sorted(tmp_path.glob("x_*.tsv")))
    assert df.height == 3 and stats["skipped_invalid"] == 0


def test_truncated_file_invalidates_the_book_for_the_next_file(tmp_path):
    # Messages were lost at the cut, so the book cannot be trusted until a fresh snapshot.
    upd = {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z", "changes": [["buy", "100.00", "2"]]}
    body = gzip.compress(("".join([L(1, SNAP)] + [L(2 + i, upd) for i in range(2000)])).encode())
    (tmp_path / "x_20261110T08.tsv.gz").write_bytes(body[:-40])
    (tmp_path / "x_20261110T09.tsv").write_text(L(9000, upd) + L(9001, SNAP) + L(9002, upd))
    df, stats = replay_files(sorted(tmp_path.glob("x_*")))
    assert stats["truncated_files"] == 1 and stats["skipped_invalid"] == 1


# ---- b4: depth must not move the spread; a depth-limited reconstruction can ----

def _naive_best(bids, asks):
    return (max(bids) if bids else None, min(asks) if asks else None)


def test_updates_below_the_top_never_move_the_spread():
    """Random changes only at levels 6+ deep, thousands of times: best bid/ask must not change.
    (The top is never removed here, so this does not exercise the heaps; the next test does.)"""
    import random
    rnd = random.Random(11)
    b = Book()
    b.snapshot([[f"{100 - i / 100:.2f}", "1"] for i in range(50)], [[f"{100.01 + i / 100:.2f}", "1"] for i in range(50)])
    top = b.best()
    for _ in range(5000):
        side = rnd.choice(["buy", "sell"])
        lvl = rnd.randint(6, 80)
        price = f"{100 - lvl / 100:.2f}" if side == "buy" else f"{100.01 + lvl / 100:.2f}"
        b.update([[side, price, rnd.choice(["0", "0.5", "2"])]])
        assert b.best()[0] == top[0] and b.best()[2] == top[2]
        assert _naive_best(b.bids, b.asks) == (b.best()[0], b.best()[2])


def test_depth_limited_book_loses_levels_it_never_kept():
    # Full book: asks at 100.01..100.07. A depth-5 book keeps 100.01..100.05 only.
    snap = {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "1"]],
            "asks": [[f"100.0{i}", "1"] for i in range(1, 8)]}
    t = "2026-10-17T12:00:00.000001Z"
    remove = {"type": "l2update", "product_id": "BTC-USD", "time": t,
              "changes": [["sell", f"100.0{i}", "0"] for i in range(1, 6)]}
    add_far = {"type": "l2update", "product_id": "BTC-USD", "time": t, "changes": [["sell", "100.09", "1"]]}
    lines = [L(1, snap), L(2, remove), L(3, add_far)]
    full = [r for r in replay_lines(lines) if "__stats__" not in r]
    d5 = [r for r in replay_lines(lines, book=Book(depth=5)) if "__stats__" not in r]
    assert [r["ask_tick"] for r in full] == [10006, 10006]
    assert [r["ask_tick"] for r in d5] == [10009]  # empty ask side first (no row), then the far level


def test_per_change_gives_one_state_after_each_change():
    upd = {"type": "l2update", "product_id": "BTC-USD", "time": "2026-10-17T12:00:00.000001Z",
           "changes": [["sell", "100.01", "0"], ["buy", "100.02", "1"], ["sell", "100.03", "0.5"]]}
    rows = [r for r in replay_lines([L(1, SNAP), L(2, upd)], per_change=True) if "__stats__" not in r]
    assert [(r["bid_tick"], r["ask_tick"]) for r in rows] == [(10000, 10003), (10002, 10003), (10002, 10003)]


def test_heap_best_matches_naive_max_min_under_random_updates_at_every_level():
    """Removals at the top are what exercise the lazy-deletion heaps."""
    import random
    rnd = random.Random(5)
    b = Book()
    b.snapshot([[f"{100 - i / 100:.2f}", "1"] for i in range(20)], [[f"{100.01 + i / 100:.2f}", "1"] for i in range(20)])
    for _ in range(5000):
        side = rnd.choice(["buy", "sell"])
        lvl = rnd.randint(0, 25)
        price = f"{100 - lvl / 100:.2f}" if side == "buy" else f"{100.01 + lvl / 100:.2f}"
        b.update([[side, price, rnd.choice(["0", "0", "1"])]])
        top = b.best()
        if b.bids and b.asks:
            assert (top[0], top[2]) == _naive_best(b.bids, b.asks)
        else:
            assert top is None
