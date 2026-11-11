"""Capture must never fail silently: it must reach TLS servers, survive refused handshakes,
and say in the raw file why each reconnect happened."""
import asyncio
import gzip
import json
from http import HTTPStatus

import websockets

from scripts_capture import run, ssl_context_for  # loaded by conftest from scripts/capture.py

SNAP = {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "1"]], "asks": [["100.01", "1"]]}


def _lines(tmp_path):
    out = []
    for p in sorted(tmp_path.glob("t_*.tsv.gz")):
        with gzip.open(p, "rt") as f:
            out += [json.loads(l.split("\t", 1)[1]) for l in f]
    return out


def test_wss_gets_a_context_with_ca_certificates():
    # python.org builds on macOS ship with no CA store, so the default context verifies nothing.
    ctx = ssl_context_for("wss://ws-feed.exchange.coinbase.com")
    assert ctx is not None and ctx.cert_store_stats()["x509_ca"] > 0
    assert ssl_context_for("ws://127.0.0.1:1") is None


def test_reconnect_marker_records_the_reason(tmp_path):
    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps(SNAP))
        await ws.close()

    async def main():
        async with websockets.serve(handler, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            return await run(f"ws://127.0.0.1:{port}", "BTC-USD", "level2_batch", tmp_path, seconds=1.5, stem="t")

    asyncio.run(main())
    markers = [m for m in _lines(tmp_path) if m["type"] == "plumb_reconnect"]
    assert markers and all(m.get("reason") for m in markers)


def test_refused_handshake_does_not_end_the_capture(tmp_path):
    calls = {"n": 0}

    def refuse_first(conn, request):
        calls["n"] += 1
        if calls["n"] == 1:
            return conn.respond(HTTPStatus.SERVICE_UNAVAILABLE, "try later\n")
        return None

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps(SNAP))
        await asyncio.sleep(5)

    async def main():
        async with websockets.serve(handler, "127.0.0.1", 0, process_request=refuse_first) as srv:
            port = srv.sockets[0].getsockname()[1]
            return await run(f"ws://127.0.0.1:{port}", "BTC-USD", "level2_batch", tmp_path, seconds=2.5, stem="t")

    stats = asyncio.run(main())
    assert stats["reconnects"] >= 1 and stats["messages"] >= 1
    assert any(m["type"] == "snapshot" for m in _lines(tmp_path))


def test_capture_stops_cleanly_when_disk_is_low(tmp_path, monkeypatch):
    import scripts_capture
    from collections import namedtuple

    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(scripts_capture.shutil, "disk_usage", lambda p: Usage(100, 100, 10 * 2**20))

    async def handler(ws):
        await ws.recv()
        while True:
            await ws.send(json.dumps(SNAP))
            await asyncio.sleep(0.01)

    async def main():
        async with websockets.serve(handler, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            return await run(f"ws://127.0.0.1:{port}", "BTC-USD", "level2_batch", tmp_path, seconds=30, stem="t",
                             min_free_bytes=2**30)

    stats = asyncio.run(main())
    assert stats["stopped"] == "low disk"
    assert stats["ended_ns"] - stats["started_ns"] < 10 * 10**9  # stopped long before the 30 s deadline
