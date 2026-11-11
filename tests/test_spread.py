from decimal import Decimal

import numpy as np
import polars as pl
import pytest

from plumb import spread as sp
from plumb.replay import to_ticks


def frame(rows):
    df = pl.DataFrame(rows, schema={"ts_ns": pl.Int64, "bid_tick": pl.Int64, "ask_tick": pl.Int64}, orient="row")
    return df.with_columns(spread_ticks=pl.col("ask_tick") - pl.col("bid_tick"))


def test_one_tick_and_two_ticks():
    df = frame([(1, 10000, 10001), (2, 10000, 10002)])
    assert df["spread_ticks"].to_list() == [1, 2]
    assert sp.share_per_event(df) == 0.5


def test_locked_is_counted_not_dropped_silently():
    kept, info = sp.clean(frame([(1, 10000, 10000), (2, 10000, 10001)]))
    assert info["locked"] == 1 and info["kept"] == 1 and info["total"] == 2


def test_crossed_is_counted():
    kept, info = sp.clean(frame([(1, 10001, 10000), (2, 10000, 10001)]))
    assert info["crossed"] == 1 and kept.height == 1


def test_float_noise_still_gives_integer_ticks():
    assert to_ticks(0.1 + 0.2, tick=Decimal("0.1")) == 3
    assert to_ticks("100.01") - to_ticks("100.00") == 1
    assert to_ticks(100.01) - to_ticks(100.0) == 1


def test_feed_gap_does_not_dominate_time_weighted_share():
    # State A (1 tick) lasts 1 s. State B (2 ticks) is followed by a 10-minute outage.
    s = 1_000_000_000
    df = frame([(0, 10000, 10001), (1 * s, 10000, 10002), (601 * s, 10000, 10001), (602 * s, 10000, 10001)])
    uncapped = sp.share_time_weighted(df, cap_ns=10**18)
    capped = sp.share_time_weighted(df, cap_ns=10 * s)
    assert uncapped < 0.01
    assert capped > 0.15


def test_gaps_lists_holes():
    s = 1_000_000_000
    df = frame([(0, 1, 2), (s // 2, 1, 2), (5 * s, 1, 2)])
    g = sp.gaps(df, threshold_ns=s)
    assert g.height == 1 and g["gap_ns"][0] == 5 * s - s // 2


def test_bootstrap_interval_covers_truth_and_widens_with_correlation():
    rng = np.random.default_rng(0)
    iid = (rng.random(50_000) < 0.5).astype(float)
    lo, hi = sp.block_bootstrap_ci(iid, block=100)
    assert lo < 0.5 < hi
    # Sticky regime series: same mean, strong autocorrelation, so the interval must be wider.
    state, sticky = 0, np.empty(50_000)
    for i in range(len(sticky)):
        if rng.random() < 0.002:
            state = 1 - state
        sticky[i] = state
    w_iid = hi - lo
    lo2, hi2 = sp.block_bootstrap_ci(sticky, block=1000)
    assert (hi2 - lo2) > 3 * w_iid


def test_bootstrap_handles_short_series():
    # Block longer than the series: no interval (it used to return a zero-width one).
    lo, hi = sp.block_bootstrap_ci(np.array([1.0, 0.0, 1.0]), block=1000, n_boot=50)
    assert np.isnan(lo) and np.isnan(hi)
    lo, hi = sp.block_bootstrap_ci(np.array([1.0, 0.0, 1.0]), block=1, n_boot=50)
    assert 0.0 <= lo <= hi <= 1.0


S = 1_000_000_000


def test_dropped_locked_time_is_not_credited_to_the_previous_state():
    # 1 tick for 1 s, then locked for 10 s, then 2 ticks for 1 s. Among kept states, each lasted 1 s.
    df = frame([(0, 10000, 10001), (1 * S, 10000, 10000), (11 * S, 10000, 10002), (12 * S, 10000, 10002)])
    s = sp.summary(df, block=1)
    assert s["locked"] == 1
    assert s["time_weighted"] == pytest.approx(0.5)


def test_grid_does_not_read_through_an_outage_or_a_locked_book():
    # 1 tick for 1 s, then a 10-minute hole, then 2 ticks for 5 s. A stale state counts for at most 10 s (cap).
    df = frame([(0, 10000, 10001), (1 * S, 10000, 10002), (601 * S, 10000, 10002), (606 * S, 10000, 10002)])
    g = sp.share_on_grid(df, step_ns=S, cap_ns=10 * S)
    # grid points 0 (1 tick); 1..11 (2 ticks, fresh within 10 s); 601..605 (2 ticks). 600 stale points dropped.
    assert g == pytest.approx(1 / 17)
    locked = frame([(0, 10000, 10001), (1 * S, 10000, 10000), (5 * S, 10000, 10001), (6 * S, 10000, 10001)])
    assert sp.share_on_grid(locked, step_ns=S) == 1.0  # the 4 locked grid points are left out, not read as 1 tick


def test_summary_counts_and_three_clocks_on_a_hand_worked_frame():
    # states every 1 s: spreads 1, 1, 2, 0 (locked), 1, -1 (crossed), 1, 3
    spreads = [1, 1, 2, 0, 1, -1, 1, 3]
    df = frame([(i * S, 10000, 10000 + d) for i, d in enumerate(spreads)])
    s = sp.summary(df, block=1)
    assert (s["total"], s["locked"], s["crossed"], s["kept"]) == (8, 1, 1, 6)
    assert s["per_event"] == pytest.approx(4 / 6)
    assert s["time_weighted"] == pytest.approx(4 / 5)  # kept states that have a duration: spreads 1,1,2,1,1
    assert s["grid_1s"] == pytest.approx(4 / 5)        # grid stops before the last time: same 5 kept points
