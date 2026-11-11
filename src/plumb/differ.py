"""Why we differ: one fixed baseline, each factor changed alone, then the two largest together.

Run: python -m plumb.differ data/raw/*.tsv.gz --out docs/local/why_we_differ.md
Numbers are derived from Coinbase data, so the output lives in docs/local/ (gitignored).
"""
from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

import polars as pl

from plumb import spread as sp
from plumb.replay import iter_rows, replay_files

THEIRS = sp.THEIRS
H_NS = 3_600_000_000_000

# docs/match-rule.md. Never changed while the table is built.
BASELINE = dict(depth=None, per_change=False, clock="per_state", locked="drop", time="ts", max_hours=None)

FACTORS = [
    {"factor": "State definition", "knob": "per_change", "variant": "a state after every change inside a batch", "set": {"per_change": True}},
    {"factor": "Depth-5 construction", "knob": "depth", "variant": "book knows only 5 levels a side", "set": {"depth": 5}},
    {"factor": "Counting rule: time-weighted", "knob": "clock", "variant": "weight by duration (cap 10 s)", "set": {"clock": "time_weighted"}},
    {"factor": "Counting rule: 1 s grid", "knob": "clock", "variant": "last state each second", "set": {"clock": "grid_1s"}},
    {"factor": "Locked and crossed books", "knob": "locked", "variant": "kept in the denominator", "set": {"locked": "keep"}},
    {"factor": "Timestamp field", "knob": "time", "variant": "receive time instead of exchange time", "set": {"time": "recv"}},
    {"factor": "Period length", "knob": "max_hours", "variant": "first 72 h only (their length)", "set": {"max_hours": 72.0}},
    {"factor": "Tick size and rounding", "knob": None, "variant": "floor instead of round-half-even", "set": None},
    {"factor": "Gap and stale-book handling", "knob": None, "variant": "no 10 s cap on durations", "set": None},
    {"factor": "Feed and channel", "knob": None, "variant": "unbatched level2 channel", "set": None},
]


@lru_cache(maxsize=4)
def _frame(paths: tuple, depth):
    df, _ = replay_files(list(paths), depth=depth)
    return df


def measure(paths, depth=None, per_change=False, clock="per_state", locked="drop", time="ts", max_hours=None):
    """Share of 1-tick states under one combination of choices. None when the combination is undefined."""
    paths = tuple(sorted(str(p) for p in paths))
    if per_change:
        if clock != "per_state":
            return None  # every change in a batch shares one timestamp: no durations, no grid
        n = one = 0
        t0 = None
        for r in iter_rows(paths, depth=depth, per_change=True):
            t = r["recv_ns"] if time == "recv" else r["ts_ns"]
            t0 = t if t0 is None else t0
            if max_hours is not None and t - t0 >= max_hours * H_NS:
                continue
            d = r["ask_tick"] - r["bid_tick"]
            if d < 1 and locked == "drop":
                continue
            n += 1
            one += d == 1
        return one / n if n else None
    df = _frame(paths, depth)
    if time == "recv":
        df = df.with_columns(ts_ns=pl.col("recv_ns"))
    df = df.sort("ts_ns", maintain_order=True).with_columns(spread_ticks=pl.col("ask_tick") - pl.col("bid_tick"))
    if max_hours is not None:
        df = df.filter(pl.col("ts_ns") < df["ts_ns"][0] + int(max_hours * H_NS))
    full = sp.add_durations(df)
    kept, _ = sp.clean(full)
    use = full if locked == "keep" else kept
    if clock == "per_state":
        return sp.share_per_event(use)
    if clock == "time_weighted":
        return sp.share_time_weighted(use)
    return sp.share_on_grid(full, keep_bad=locked == "keep")


def off_tick_prices(paths) -> tuple[int, int]:
    """(prices not on the 0.01 grid, prices checked). If the first is 0, floor and round cannot differ."""
    pat = re.compile(r'"(\d+)\.(\d+)"')
    bad = seen = 0
    for p in paths:
        opener = gzip.open if str(p).endswith(".gz") else open
        try:
            with opener(p, "rt") as f:
                for line in f:
                    raw = line.split("\t", 1)[1]
                    if '"l2update"' not in raw and '"snapshot"' not in raw:
                        continue
                    m = json.loads(raw)
                    prices = [c[1] for c in m.get("changes", [])] + [x[0] for x in m.get("bids", []) + m.get("asks", [])]
                    for price in prices:
                        seen += 1
                        bad += len(price.split(".")[1]) > 2 if "." in price else 0
        except EOFError:
            pass  # truncated file: what was read counts
    return bad, seen


def build(paths, max_hours: float = 72.0) -> dict:
    base = measure(paths, **BASELINE)
    rows = []
    for f in FACTORS:
        row = {"factor": f["factor"], "knob": f["knob"], "variant": f["variant"], "value": None,
               "change_points": None, "note": ""}
        if f["set"] is not None:
            kw = {**BASELINE, **f["set"]}
            if f["knob"] == "max_hours":
                kw["max_hours"] = max_hours
            v = measure(paths, **kw)
            row["value"] = v
            row["change_points"] = None if v is None else round((v - base) * 100, 4)
        elif f["factor"] == "Tick size and rounding":
            bad, seen = off_tick_prices(paths)
            row["change_points"] = 0.0 if bad == 0 else None
            row["note"] = f"{seen:,} prices checked, {bad} off the 0.01 grid" + ("; floor and round agree on every one" if bad == 0 else "; not measured")
        elif f["factor"] == "Gap and stale-book handling":
            row["change_points"] = 0.0
            row["note"] = "the baseline counts states, not time, so a cap on durations cannot move it (it moves the time-weighted share only)"
        else:
            row["note"] = "not testable: the unbatched level2 channel needs authentication, which this project does not use"
        rows.append(row)
    measured = sorted([r for r in rows if r["change_points"] is not None], key=lambda r: -abs(r["change_points"]))
    rest = [r for r in rows if r["change_points"] is None]
    combinable = [r for r in measured if r["knob"]]
    pairs = [(x, y) for i, x in enumerate(combinable) for y in combinable[i + 1:] if x["knob"] != y["knob"]]

    def together(x, y):
        kw = {**BASELINE, **next(f["set"] for f in FACTORS if f["factor"] == x["factor"]),
              **next(f["set"] for f in FACTORS if f["factor"] == y["factor"])}
        if kw.get("max_hours"):
            kw["max_hours"] = max_hours
        v = measure(paths, **kw)
        return {"factors": [x["factor"], y["factor"]], "value": v,
                "change_points": None if v is None else round((v - base) * 100, 4),
                "gap_before_points": round((base - THEIRS) * 100, 4),
                "gap_after_points": None if v is None else round((v - THEIRS) * 100, 4)}

    combined = together(*pairs[0])
    if combined["value"] is None:
        combined["note"] = ("undefined: per-change states all share their batch's timestamp, "
                            "so they have no durations and no grid position")
        combined["fallback"] = next((c for c in (together(*p) for p in pairs[1:]) if c["value"] is not None), None)
    return {"baseline": base, "theirs": THEIRS, "rows": measured + rest, "combined": combined}


def markdown(t: dict) -> str:
    pct = lambda x: "n/a" if x is None else f"{100 * x:.3f}%"
    pts = lambda x: "not measured" if x is None else f"{x:+.2f}"
    out = [f"Baseline (docs/match-rule.md): {pct(t['baseline'])}. Theirs: {pct(t['theirs'])}. "
           f"Gap: {pts(t['combined']['gap_before_points'])} points.", "",
           "| Factor | Variant | Share | Change (points) | Note |", "|---|---|---|---|---|"]
    out += [f"| {r['factor']} | {r['variant']} | {pct(r['value'])} | {pts(r['change_points'])} | {r['note']} |" for r in t["rows"]]
    def line(label, c):
        return (f"{label} ({' + '.join(c['factors'])}): {pct(c['value'])}, change {pts(c['change_points'])} points; "
                f"gap to theirs {pts(c['gap_before_points'])} before, {pts(c['gap_after_points'])} after.")
    c = t["combined"]
    out += ["", line("Two largest together", c) if c["value"] is not None else
            f"Two largest together ({' + '.join(c['factors'])}): {c['note']}."]
    if c.get("fallback"):
        out.append(line("Next largest pair that is defined", c["fallback"]))
    return "\n".join(out)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="+")
    ap.add_argument("--out", default="docs/local/why_we_differ.md")
    ap.add_argument("--max-hours", type=float, default=72.0)
    a = ap.parse_args()
    t = build(a.raw, max_hours=a.max_hours)
    md = markdown(t)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md + "\n")
    Path(a.out).with_suffix(".json").write_text(json.dumps(t, indent=2))
    print(md)
