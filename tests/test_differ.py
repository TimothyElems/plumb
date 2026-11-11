"""b4: one baseline, each factor alone, the two largest together."""
from pathlib import Path

import pytest

RAW = [Path(__file__).resolve().parents[1] / "data" / "sample" / "synthetic_raw.tsv.gz"]


def test_baseline_matches_the_results_number():
    from plumb import spread as sp
    from plumb.differ import BASELINE, measure
    from plumb.replay import replay_files
    df, _ = replay_files(RAW)
    kept, _ = sp.clean(sp.add_durations(df.sort("ts_ns").with_columns(spread_ticks=df["ask_tick"] - df["bid_tick"])))
    assert measure(RAW, **BASELINE) == pytest.approx(sp.share_per_event(kept))


def test_table_is_sorted_by_size_and_combines_the_two_largest():
    from plumb.differ import FACTORS, build
    t = build(RAW, max_hours=1.0)
    rows = [r for r in t["rows"] if r["change_points"] is not None]
    sizes = [abs(r["change_points"]) for r in rows]
    assert sizes == sorted(sizes, reverse=True)
    assert {r["factor"] for r in t["rows"]} == {f["factor"] for f in FACTORS}
    top2 = t["combined"]
    combinable = [r for r in rows if r["knob"]]
    second = next(r for r in combinable[1:] if r["knob"] != combinable[0]["knob"])  # two clocks cannot both apply
    assert top2["factors"] == [combinable[0]["factor"], second["factor"]]
    assert "change_points" in top2 and "gap_after_points" in top2


def test_untestable_factor_is_listed_not_invented():
    from plumb.differ import build
    t = build(RAW, max_hours=1.0)
    feed = next(r for r in t["rows"] if r["factor"] == "Feed and channel")
    assert feed["change_points"] is None and "authentication" in feed["note"]


def test_per_change_with_a_time_clock_is_undefined():
    from plumb.differ import measure
    assert measure(RAW, per_change=True, clock="time_weighted") is None


def test_undefined_top_pair_says_why_and_reports_the_next_defined_pair():
    from plumb.differ import build
    t = build(RAW, max_hours=1.0)
    c = t["combined"]
    if c["value"] is None:
        assert "undefined" in c["note"]
        assert c["fallback"]["value"] is not None and len(c["fallback"]["factors"]) == 2


def test_per_change_respects_depth():
    from plumb.differ import measure
    from plumb.replay import iter_rows
    rows = list(iter_rows(RAW, depth=5, per_change=True))
    spreads = [r["ask_tick"] - r["bid_tick"] for r in rows]
    kept = [d for d in spreads if d >= 1]
    expected = sum(d == 1 for d in kept) / len(kept)
    assert measure(RAW, per_change=True, depth=5) == pytest.approx(expected)
    assert measure(RAW, per_change=True, depth=5) != measure(RAW, per_change=True)
