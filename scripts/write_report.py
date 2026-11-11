"""Write the full report, with numbers, from report/local/results.json and docs/local/why_we_differ.json.

Run: python scripts/write_report.py   (after `make result` and `python -m plumb.differ ...`)
Output: report/local/report.md. It holds numbers derived from Coinbase data, so it stays local (README).
Refuses synthetic results: the Result fields are filled from real numbers or not at all.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def pct(x, d=2):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def utc(ns):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ns / 1e9))


def render(r: dict, w: dict) -> str:
    if r.get("synthetic"):
        raise ValueError("refusing to write a report from synthetic sample data")
    v, c = r["verdict"], r["counts"]
    if not v.get("usable", False):
        raise ValueError("the block-1,000 interval has too few blocks; record more data before reporting")
    matched = "matched" if v["theirs_inside"] else "did not match"
    where = "inside" if v["theirs_inside"] else "outside"
    blocks = {b["block"]: b for b in r["blocks"]}
    hod = [h for h in r["hour_of_day"] if h["share"] is not None]
    lo_h = min(hod, key=lambda h: h["share"])
    hi_h = max(hod, key=lambda h: h["share"])
    hours = (r["last_ts_ns"] - r["first_ts_ns"]) / 3_600e9

    out = [
        "# Plumb: BTC-USD spread, tested",
        "",
        f"**Result:** I measured {pct(v['share'])} (95% CI {pct(v['lo'])} to {pct(v['hi'])}, block bootstrap, block 1,000) "
        f"for the share of BTC-USD book states with a one-tick spread, against their 55.60%. "
        f"Gap: {v['gap_points']:+.2f} points; their number lies {where} my interval, so under the rule written before any data, "
        f"I {matched}.",
        "",
        f"Measured on my own recording of Coinbase's public `level2_batch` feed, {utc(r['first_ts_ns'])} to {utc(r['last_ts_ns'])} "
        f"({hours:.1f} hours), one state per 50 ms batch, full-depth book, locked and crossed books dropped. "
        "Definitions and the match rule were committed before any data was recorded (docs/definitions.md, docs/match-rule.md).",
        "",
    ]
    if r["interval_grows_with_block"]:
        out += [f"**The interval depends on block length.** At block 100 it is {pct(blocks[100]['lo'])} to {pct(blocks[100]['hi'])}; "
                f"at block 10,000 it is {pct(blocks[10000]['lo'])} to {pct(blocks[10000]['hi'])}. Neighbouring states are correlated "
                "over long stretches, so the short-block interval is too narrow. The verdict uses block 1,000, as fixed in advance.", ""]

    out += ["## Definitions", "",
            "Their wording, my values and each assumption (A1–A8) are in docs/definitions.md. The ones that matter most: "
            "their \"book states\" are about 113 a second (29,263,059 over three days); my batches are at most 20 a second (A1). "
            "Their book was \"reconstructed to depth five\"; mine is full depth (A5). Their dates are not stated (A2).", "",
            "## Data", "",
            f"Coinbase Exchange websocket, `level2_batch`, BTC-USD. {c['total']:,} states; {c['locked']:,} locked and {c['crossed']:,} "
            f"crossed, dropped from the denominator ({c['kept']:,} kept). {c['gaps_over_1s']} gaps over 1 s, {c['gap_seconds']:.1f} s in total. "
            "Hashes, reconnects and every gap: data/MANIFEST.md.", "",
            "## Method", "",
            "Prices become integer ticks through `Decimal`, so \"one tick\" is an integer comparison. Spread = best ask − best bid. "
            "Three counting rules: per state (the verdict), time-weighted (each state capped at 10 s), and a 1 s grid "
            "(a grid point is skipped if its state is locked, crossed or older than 10 s). Moving-block bootstrap, 2,000 resamples, "
            "seed 7, blocks of 100, 1,000 and 10,000 states. Ten states were checked by hand against an independent replay (docs/hand-check.md).", "",
            "## Results", "",
            "| Clock | Share |", "|---|---|",
            f"| Per state (verdict) | {pct(r['clocks']['per_state'])} |",
            f"| Time-weighted | {pct(r['clocks']['time_weighted'])} |",
            f"| 1 s grid | {pct(r['clocks']['grid_1s'])} |", "",
            "| Block length | Blocks | 95% interval |", "|---|---|---|"]
    out += [f"| {b['block']:,} | {b['n_blocks']:,} | {pct(b['lo'])} to {pct(b['hi'])}{' (too few blocks)' if b['too_few_blocks'] else ''} |"
            for b in r["blocks"]]
    out += ["", f"By hour of day (UTC), the share runs from {pct(lo_h['share'])} at {lo_h['hour_utc']:02d}:00 to "
                f"{pct(hi_h['share'])} at {hi_h['hour_utc']:02d}:00, so the recording period matters. "
                "Figure: figures/share_by_hour.png.", "",
            "## Why we differ", "",
            "One factor at a time from the baseline, sorted by size. Method: docs/why_we_differ.md.", "",
            "| Factor | Variant | Change (points) | Note |", "|---|---|---|---|"]
    for row in w["rows"]:
        ch = "not measured" if row["change_points"] is None else f"{row['change_points']:+.2f}"
        out.append(f"| {row['factor']} | {row['variant']} | {ch} | {row['note']} |")
    cmb = w["combined"]
    pair = cmb if cmb["value"] is not None else cmb.get("fallback")
    if cmb["value"] is None:
        out += ["", f"The two largest ({' + '.join(cmb['factors'])}) cannot be combined: {cmb['note']}."]
    if pair:
        closes = abs(pair["gap_after_points"]) < abs(pair["gap_before_points"])
        out += ["", f"Together, {' + '.join(pair['factors'])} move the share by {pair['change_points']:+.2f} points. The gap goes from "
                    f"{pair['gap_before_points']:+.2f} to {pair['gap_after_points']:+.2f} points"
                    + (", so it narrows." if closes else ", so it does not narrow.")]
    out += ["", "**Still unexplained.** The unbatched `level2` channel could not be tested (it needs authentication), and their "
                "dates are unknown, so whatever gap remains is listed here, not explained away.", "",
            "## Limits", "",
            "- One venue (Coinbase Exchange) and one product (BTC-USD).",
            "- My own recording period, not theirs. Their dates are not published.",
            "- One clock family: states, time and a grid, all from the same batched book.",
            "- A batched feed: `level2_batch` groups updates every 50 ms, so a state is a batch, not an exchange event.",
            "- I never saw their data or their code. Everything about their method comes from one published page.", "",
            "## Rerun", "",
            "`make capture replay result`, then `python -m plumb.differ data/raw/*.tsv.gz` and `python scripts/write_report.py`."]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    r = json.loads((ROOT / "report/local/results.json").read_text())
    w = json.loads((ROOT / "docs/local/why_we_differ.json").read_text())
    out = ROOT / "report/local/report.md"
    out.write_text(render(r, w))
    print(f"wrote {out}")
