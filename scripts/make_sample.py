"""Write a SYNTHETIC raw capture, then replay it to data/sample/book.parquet.

The numbers are invented. This exists so tests and CI run without network access
and so you can try the whole path before you record real data. Never report it as a result.
"""
import gzip
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from plumb.replay import replay_files  # noqa: E402


def main(out_raw="data/sample/synthetic_raw.tsv.gz", out_pq="data/sample/book.parquet", n=5000, seed=3):
    rnd = random.Random(seed)
    mid = 6_700_000  # ticks
    bids = {mid - i: 1.0 for i in range(1, 30)}
    asks = {mid + i: 1.0 for i in range(1, 30)}
    t = 1_792_238_400_000_000_000  # fixed start, nanoseconds
    lines = []
    fmt = lambda tk: f"{tk / 100:.2f}"
    lines.append(f"{t}\t" + json.dumps({"type": "snapshot", "product_id": "BTC-USD",
                 "bids": [[fmt(p), str(s)] for p, s in bids.items()], "asks": [[fmt(p), str(s)] for p, s in asks.items()]}))
    for _ in range(n):
        t += 50_000_000
        ch = []
        for _ in range(rnd.randint(1, 4)):
            bb, ba = max(bids), min(asks)
            if rnd.random() < 0.5:
                p = min(bb + rnd.choice([-2, -1, 0, 1]), ba - 1)
                s = rnd.choice([0, 0.2, 0.5, 1.0])
                if s == 0 and (len(bids) <= 5 or p not in bids):
                    s = 0.2
                (bids.__setitem__(p, s) if s else bids.pop(p, None))
                ch.append(["buy", fmt(p), str(s)])
            else:
                p = max(ba + rnd.choice([-1, 0, 1, 2]), bb + 1)
                s = rnd.choice([0, 0.2, 0.5, 1.0])
                if s == 0 and (len(asks) <= 5 or p not in asks):
                    s = 0.2
                (asks.__setitem__(p, s) if s else asks.pop(p, None))
                ch.append(["sell", fmt(p), str(s)])
        secs, ns = divmod(t, 1_000_000_000)
        import time as _t
        iso = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime(secs)) + f".{ns // 1000:06d}Z"
        lines.append(f"{t}\t" + json.dumps({"type": "l2update", "product_id": "BTC-USD", "time": iso, "changes": ch}))
    Path(out_raw).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_raw, "wt") as f:
        f.write("\n".join(lines) + "\n")
    df, stats = replay_files([out_raw])
    df.write_parquet(out_pq)
    print(stats)
    print(f"wrote {df.height} rows to {out_pq}")


if __name__ == "__main__":
    main()
