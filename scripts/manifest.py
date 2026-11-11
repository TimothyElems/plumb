"""Print the measured half of data/MANIFEST.md: hashes, capture window, rows, every reconnect, every gap.

Run: python scripts/manifest.py data/raw/*.tsv.gz data/book.parquet
The last argument is the Parquet file; every other argument is a raw capture file.
"""
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl  # noqa: E402

from plumb.spread import gaps  # noqa: E402

GAP_NS = 1_000_000_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc(ns: int) -> str:
    sec, frac = divmod(int(ns), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + f".{frac // 1000:06d}Z"


def scan_raw(path: Path):
    """First and last receive time, line count, and the reconnect markers of one raw file."""
    first = last = None
    n = 0
    reconnects = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            n += 1
            recv, _, raw = line.partition("\t")
            ns = int(recv)
            first = ns if first is None else first
            last = ns
            if '"plumb_reconnect"' in raw:
                reconnects.append((ns, json.loads(raw).get("reason", "(no reason recorded)")))
    return first, last, n, reconnects


def build_manifest(raw_paths, parquet_path) -> str:
    raw_paths = sorted(Path(p) for p in raw_paths)
    pq = Path(parquet_path)
    out = ["| file | bytes | lines | first receive (UTC) | last receive (UTC) | sha256 |", "|---|---|---|---|---|---|"]
    starts, ends, reconnects = [], [], []
    for p in raw_paths:
        first, last, n, rc = scan_raw(p)
        starts.append(first)
        ends.append(last)
        reconnects += rc
        out.append(f"| {p.name} | {p.stat().st_size} | {n} | {utc(first)} | {utc(last)} | `{sha256(p)}` |")
    df = pl.read_parquet(pq).sort("ts_ns")
    out.append(f"| {pq.name} | {pq.stat().st_size} | | | | `{sha256(pq)}` |")

    g = gaps(df, threshold_ns=GAP_NS)
    out += ["", "| field | value |", "|---|---|",
            f"| Capture start (UTC, first receive) | {utc(min(starts))} |",
            f"| Capture end (UTC, last receive) | {utc(max(ends))} |",
            f"| Hours recorded | {(max(ends) - min(starts)) / 3.6e12:.2f} |",
            f"| Rows | {df.height} |",
            f"| First / last state (exchange time) | {utc(df['ts_ns'][0])} / {utc(df['ts_ns'][-1])} |",
            f"| Reconnects | {len(reconnects)} |",
            f"| Gaps over 1 s | {g.height} |",
            f"| Gap time, total s | {g['gap_ns'].sum() / 1e9:.3f} |",
            f"| Longest gap, s | {(g['gap_ns'].max() or 0) / 1e9:.3f} |"]

    out += ["", "### Reconnects", "", "| receive time (UTC) | reason |", "|---|---|"]
    out += [f"| {utc(ns)} | {reason} |" for ns, reason in reconnects] or ["| none | |"]
    out += ["", "### Gaps over 1 s (exchange time between consecutive states)", "",
            "| from (UTC) | to (UTC) | seconds |", "|---|---|---|"]
    out += [f"| {utc(a)} | {utc(b)} | {d / 1e9:.3f} |" for a, b, d in g.iter_rows()] or ["| none | | |"]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: manifest.py RAW... BOOK.parquet")
    print(build_manifest(sys.argv[1:-1], sys.argv[-1]))
