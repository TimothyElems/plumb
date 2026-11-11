"""Every number the report needs, from one Parquet file, in one JSON file.

Run: python -m plumb.results data/book.parquet --out report/local/results.json
The output is derived from Coinbase data, so it lives in report/local/ (gitignored). See README.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from plumb import spread as sp

VERDICT_BLOCK = 1000  # fixed in docs/match-rule.md before any data


def _f(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else x


def run(path: str, out: Path | None, n_boot: int = 2000, synthetic: bool = False) -> dict:
    df = sp.load(path)
    full = sp.add_durations(df)
    kept, counts = sp.clean(full)
    ind = (kept["spread_ticks"] == 1).to_numpy()
    blocks = sp.block_sweep(ind, blocks=(100, VERDICT_BLOCK, 10000), n_boot=n_boot)
    b = next(r for r in blocks if r["block"] == VERDICT_BLOCK)
    share = float(ind.mean())
    g = sp.gaps(df)
    hod = sp.by_hour_of_day(kept, block=VERDICT_BLOCK, n_boot=max(200, n_boot // 2))
    r = {
        "source": str(path),
        "synthetic": bool(synthetic or "data/sample" in str(path)),
        "first_ts_ns": int(df["ts_ns"][0]), "last_ts_ns": int(df["ts_ns"][-1]),
        "counts": {**counts, "gaps_over_1s": g.height, "gap_seconds": float(g["gap_ns"].sum() / 1e9)},
        "clocks": {"per_state": share, "time_weighted": sp.share_time_weighted(kept),
                   "grid_1s": sp.share_on_grid(full)},
        "blocks": [{k: _f(v) for k, v in row.items()} for row in blocks],
        "interval_grows_with_block": sp.interval_grows(blocks),
        "verdict": {"block": VERDICT_BLOCK, "usable": not b["too_few_blocks"],
                    **{k: _f(v) for k, v in sp.verdict(share, b["lo"], b["hi"]).items()}},
        "hour_of_day": [{k: _f(v) for k, v in row.items()} for row in hod.to_dicts()],
    }
    if out is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(r, indent=2))
    return r


def show(r: dict) -> None:
    pct = lambda x: "  n/a  " if x is None else f"{100 * x:7.3f}%"
    print("SYNTHETIC SAMPLE: NOT A RESULT" if r["synthetic"] else f"source: {r['source']}")
    print("counts:", r["counts"])
    for k, v in r["clocks"].items():
        print(f"  {k:<14}{pct(v)}")
    print("block bootstrap, per state:")
    for b in r["blocks"]:
        flag = "  TOO FEW BLOCKS" if b["too_few_blocks"] else ""
        print(f"  block {b['block']:>6}  blocks {b['n_blocks']:>6}  [{pct(b['lo'])}, {pct(b['hi'])}]{flag}")
    print("interval grows with block length:", r["interval_grows_with_block"])
    v = r["verdict"]
    print(f"verdict (block {v['block']}): mine {pct(v['share'])} theirs {pct(v['theirs'])} "
          f"gap {v['gap_points']:+.2f} points, theirs inside my interval: {v['theirs_inside']}"
          + ("" if v["usable"] else "  (NOT USABLE: too few blocks)"))
    print("hour of day (UTC):")
    for h in r["hour_of_day"]:
        print(f"  {h['hour_utc']:02d}  n {h['n']:>8}  days {h['days']}  {pct(h['share'])} [{pct(h['lo'])}, {pct(h['hi'])}]")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("parquet")
    ap.add_argument("--out", default="report/local/results.json")
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()
    show(run(a.parquet, Path(a.out), n_boot=a.n_boot))
