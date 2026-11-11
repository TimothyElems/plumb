"""Record the Coinbase Exchange level2_batch feed, unchanged, to hourly gzip files.

Each line: "<recv_ns>\t<raw message text>". Nothing is parsed or filtered, so the files are the
provenance. Reconnects write a marker line so the replay knows the book is invalid until the next snapshot.

Feed facts, from Coinbase's public docs (re-check them before you rely on them):
- Endpoint wss://ws-feed.exchange.coinbase.com needs no authentication.
- level2 needs authentication. level2_batch does not, and it batches updates every 50 ms.
  That means each state is one batch, not one exchange event. Say so in the report.
Run: python scripts/capture.py --hours 24
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import shutil
import ssl
import sys
import time
from pathlib import Path

import certifi
import websockets

URL = "wss://ws-feed.exchange.coinbase.com"


def ssl_context_for(url: str) -> ssl.SSLContext | None:
    """Verify TLS against certifi's CA bundle.

    python.org builds on macOS ship without a CA store. With the default context every handshake
    fails, and a capture that treats that as a reconnect records nothing for 24 hours.
    """
    return ssl.create_default_context(cafile=certifi.where()) if url.startswith("wss://") else None


class HourlyWriter:
    def __init__(self, out_dir: Path, stem: str):
        self.dir, self.stem = out_dir, stem
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hour, self.f, self.n = None, None, 0

    def write(self, recv_ns: int, raw: str) -> None:
        hour = time.strftime("%Y%m%dT%H", time.gmtime(recv_ns / 1e9))
        if hour != self.hour:
            self.close()
            self.hour = hour
            self.f = gzip.open(self.dir / f"{self.stem}_{hour}.tsv.gz", "at", encoding="utf-8")
        self.f.write(f"{recv_ns}\t{raw}\n")
        self.n += 1
        if self.n % 200 == 0:
            self.f.flush()  # sync flush, so a crash leaves a readable file

    def close(self) -> None:
        if self.f:
            self.f.close()
            self.f = None


async def run(url: str, product: str, channel: str, out_dir: Path, seconds: float, stem: str | None = None,
              min_free_bytes: int = 0) -> dict:
    """Record until the deadline, or stop early (and say so) if free disk falls below min_free_bytes."""
    stem = stem or f"{product.replace('-', '').lower()}_{channel}"
    writer = HourlyWriter(out_dir, stem)
    stats = {"messages": 0, "reconnects": 0, "started_ns": time.time_ns(), "stopped": "deadline"}

    def disk_low() -> bool:
        return min_free_bytes > 0 and shutil.disk_usage(out_dir).free < min_free_bytes

    deadline = time.monotonic() + seconds
    backoff = 1.0
    try:
        while time.monotonic() < deadline:
            try:
                async with websockets.connect(url, max_size=None, ping_interval=20, ssl=ssl_context_for(url)) as ws:
                    await ws.send(json.dumps({"type": "subscribe", "product_ids": [product], "channels": [channel]}))
                    backoff = 1.0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                        except asyncio.TimeoutError:
                            continue
                        writer.write(time.time_ns(), raw if isinstance(raw, str) else raw.decode())
                        stats["messages"] += 1
                        if stats["messages"] % 100 == 0 and disk_low():
                            stats["stopped"] = "low disk"
                            print("stopping: free disk below the limit", file=sys.stderr, flush=True)
                            break
                reason = "server stopped sending before the deadline"
            except (websockets.WebSocketException, OSError, asyncio.TimeoutError) as e:
                # WebSocketException covers ConnectionClosed and refused handshakes (InvalidStatus).
                reason = f"{type(e).__name__}: {e}"
            if stats["stopped"] != "deadline":
                break
            if time.monotonic() < deadline:
                stats["reconnects"] += 1
                print(f"reconnect {stats['reconnects']}: {reason}", file=sys.stderr, flush=True)
                writer.write(time.time_ns(), json.dumps({"type": "plumb_reconnect", "reason": reason}))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
    finally:
        writer.close()
    stats["ended_ns"] = time.time_ns()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--product", default="BTC-USD")
    ap.add_argument("--channel", default="level2_batch")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--min-free-gb", type=float, default=1.0, help="stop cleanly below this much free disk")
    a = ap.parse_args()
    print(asyncio.run(run(a.url, a.product, a.channel, Path(a.out), a.hours * 3600,
                          min_free_bytes=int(a.min_free_gb * 2**30))), flush=True)
