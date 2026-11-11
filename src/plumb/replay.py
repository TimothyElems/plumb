"""Replay raw Coinbase level2 messages into a top-of-book table.

Input lines: "<recv_ns>\t<raw json>". Output: Parquet with integer ticks, so no float
comparison ever decides whether a spread is one tick.

Rules, all stated on purpose:
- A snapshot replaces the whole book.
- l2update sets each level to the new total size. Size 0 removes the level.
- One output row per l2update message. On level2_batch that is one row per batch,
  not one row per exchange event. This is a known difference from per-event data.
- The book carries across files: the capture rolls to a new file every hour and the snapshot is
  only sent at connect. A truncated file (capture killed mid-write) invalidates the book.
- A reconnect marker invalidates the book. No rows are written until the next snapshot.
- Every output column is Int64: times in ns, prices in ticks (0.01 USD), sizes in satoshi (1e-8 BTC).
"""
from __future__ import annotations

import calendar
import gzip
from array import array
import heapq
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

TICK = Decimal("0.01")  # BTC-USD. Confirmed 2026-11-10: GET /products/BTC-USD, quote_increment "0.01".
SIZE_UNIT = Decimal("0.00000001")  # base_increment: sizes become integer satoshi.
COLUMNS = ("ts_ns", "recv_ns", "bid_tick", "ask_tick", "bid_sz", "ask_sz")


def to_ticks(price: str | float | Decimal, tick: Decimal = TICK) -> int:
    """Exact integer ticks. Strings go through Decimal. Floats are rounded, not floored."""
    d = Decimal(str(price)) if not isinstance(price, Decimal) else price
    return int((d / tick).to_integral_value(rounding="ROUND_HALF_EVEN"))


def parse_time_ns(s: str) -> int:
    """'2026-11-10T08:23:31.944193Z' to integer nanoseconds, keeping every digit.

    Coinbase sends 6 fractional digits today (checked 2026-11-10). The fraction is parsed as a string
    so 7 to 9 digits would also be kept exactly; datetime alone would silently drop them.
    """
    if not s.endswith("Z"):
        raise ValueError(f"expected a UTC time ending in Z: {s!r}")
    base, _, frac = s[:-1].partition(".")
    if len(frac) > 9 or (frac and not frac.isdigit()):
        raise ValueError(f"bad fractional seconds: {s!r}")
    secs = calendar.timegm(datetime.fromisoformat(base).timetuple())
    return secs * 1_000_000_000 + int(frac.ljust(9, "0") or 0)


class Book:
    """Two dicts for sizes, two heaps for best price with lazy deletion.

    depth=None keeps every level (the baseline). depth=N is a deliberately lossy variant for
    docs/why_we_differ.md: the book only ever knows N levels a side, and a change outside them
    is thrown away, so when the top empties it cannot know the true next level."""

    def __init__(self, tick: Decimal = TICK, depth: int | None = None):
        self.tick = tick
        self.depth = depth
        self.reset()

    def reset(self) -> None:
        self.bids: dict[int, int] = {}  # tick -> size in satoshi
        self.asks: dict[int, int] = {}
        self._bh: list[int] = []  # negated bid ticks
        self._ah: list[int] = []
        self.valid = False

    def snapshot(self, bids, asks) -> None:
        self.reset()
        for p, s in bids:
            self._set("buy", to_ticks(p, self.tick), to_ticks(s, SIZE_UNIT))
        for p, s in asks:
            self._set("sell", to_ticks(p, self.tick), to_ticks(s, SIZE_UNIT))
        self.valid = True

    def update(self, changes) -> None:
        for side, p, s in changes:
            self._set(side, to_ticks(p, self.tick), to_ticks(s, SIZE_UNIT))

    def _set(self, side: str, tick: int, size: int) -> None:
        buy = side == "buy"
        book, heap, key = (self.bids, self._bh, -tick) if buy else (self.asks, self._ah, tick)
        if size == 0:
            book.pop(tick, None)
        elif tick in book:
            book[tick] = size
        else:
            if self.depth is not None and len(book) >= self.depth:
                worst = min(book) if buy else max(book)
                if (tick <= worst) if buy else (tick >= worst):
                    return  # outside the levels this book keeps
                book.pop(worst)
            heapq.heappush(heap, key)
            book[tick] = size

    def best(self):
        while self._bh and (-self._bh[0]) not in self.bids:
            heapq.heappop(self._bh)
        while self._ah and self._ah[0] not in self.asks:
            heapq.heappop(self._ah)
        if not self._bh or not self._ah:
            return None
        b, a = -self._bh[0], self._ah[0]
        return b, self.bids[b], a, self.asks[a]


def _open(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else open(path, encoding="utf-8")


def _lines_until_cut(f, flag: dict):
    """Yield lines; stop quietly at the end of a truncated gzip stream and record that it happened."""
    try:
        yield from f
    except EOFError:
        flag["truncated"] = True


def replay_lines(lines, tick: Decimal = TICK, book: Book | None = None, per_change: bool = False):
    """Yield dict rows. Also returns counts through the 'stats' dict on the generator's last item.

    Pass the same `book` for consecutive files of one capture so the state carries over.
    per_change=True yields a state after every change inside a batch, all with the batch's time:
    the closest this feed gets to per-event states (a why-we-differ variant, not the baseline)."""
    book = book if book is not None else Book(tick)
    stats = {"lines": 0, "bad_lines": 0, "snapshots": 0, "updates": 0, "reconnects": 0, "rows": 0, "skipped_invalid": 0}
    for line in lines:
        stats["lines"] += 1
        try:
            recv, raw = line.rstrip("\n").split("\t", 1)
            msg = json.loads(raw)
            recv_ns = int(recv)
        except (ValueError, json.JSONDecodeError):
            stats["bad_lines"] += 1
            continue
        kind = msg.get("type")
        if kind == "plumb_reconnect":
            stats["reconnects"] += 1
            book.reset()
        elif kind == "snapshot":
            stats["snapshots"] += 1
            book.snapshot(msg["bids"], msg["asks"])
        elif kind == "l2update":
            stats["updates"] += 1
            if not book.valid:
                stats["skipped_invalid"] += 1
                continue
            ts_ns = parse_time_ns(msg["time"])
            steps = [[c] for c in msg["changes"]] if per_change else [msg["changes"]]
            for changes in steps:
                book.update(changes)
                top = book.best()
                if top is None:
                    stats["skipped_invalid"] += 1
                    continue
                bt, bs, at, asz = top
                stats["rows"] += 1
                yield {"ts_ns": ts_ns, "recv_ns": recv_ns,
                       "bid_tick": bt, "ask_tick": at, "bid_sz": bs, "ask_sz": asz}
    yield {"__stats__": stats}


def iter_rows(paths, tick: Decimal = TICK, depth: int | None = None, per_change: bool = False, stats: dict | None = None):
    """Rows from every file of one capture, in name order (hourly names sort by time), one book throughout.
    Streams, so a variant with ~100 million states never has to sit in memory."""
    stats = {} if stats is None else stats
    stats.setdefault("truncated_files", 0)
    book = Book(tick, depth=depth)
    for path in sorted(Path(p) for p in paths):
        flag = {"truncated": False}
        with _open(path) as f:
            for r in replay_lines(_lines_until_cut(f, flag), tick, book, per_change):
                if "__stats__" in r:
                    for k, v in r["__stats__"].items():
                        stats[k] = stats.get(k, 0) + v
                else:
                    yield r
        if flag["truncated"]:
            stats["truncated_files"] += 1
            book.reset()


def replay_files(paths, tick: Decimal = TICK, depth: int | None = None, per_change: bool = False):
    """All rows as one DataFrame. Columns are packed int64 arrays, so days of data fit in memory:
    8 bytes a value, not a Python dict per row."""
    cols = {c: array("q") for c in COLUMNS}
    stats: dict[str, int] = {}
    for r in iter_rows(paths, tick, depth, per_change, stats):
        for c in COLUMNS:
            cols[c].append(r[c])
    df = pl.DataFrame({c: pl.Series(c, cols[c], dtype=pl.Int64) for c in COLUMNS})
    return df, stats


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Raw capture files to one Parquet file.")
    ap.add_argument("raw", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df, stats = replay_files(a.raw)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(a.out)
    print(stats, file=sys.stderr)
    print(f"wrote {df.height} rows to {a.out}")
