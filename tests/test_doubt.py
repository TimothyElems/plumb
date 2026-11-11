"""b3: interval sensitivity to block length, the verdict, and the share by hour of day."""
import numpy as np
import polars as pl
import pytest

from plumb import spread as sp

H = 3_600_000_000_000


def sticky(n, p_switch, seed=0):
    rng = np.random.default_rng(seed)
    flips = rng.random(n) < p_switch
    return (np.cumsum(flips) % 2).astype(float)


def test_block_sweep_reports_all_three_and_flags_growth():
    rows = sp.block_sweep(sticky(200_000, 0.001), blocks=(100, 1000, 10000))
    assert [r["block"] for r in rows] == [100, 1000, 10000]
    assert all(r["lo"] <= r["hi"] for r in rows)
    assert rows[2]["width"] > 2 * rows[0]["width"]
    assert sp.interval_grows(rows)


def test_block_sweep_does_not_flag_growth_on_independent_data():
    rng = np.random.default_rng(1)
    rows = sp.block_sweep((rng.random(200_000) < 0.5).astype(float), blocks=(100, 1000, 10000))
    assert not sp.interval_grows(rows)


def test_too_few_blocks_is_flagged_not_reported_as_a_tight_interval():
    rows = sp.block_sweep(sticky(5_000, 0.01), blocks=(100, 10000))
    assert rows[0]["too_few_blocks"] is False
    assert rows[1]["n_blocks"] == 0 and rows[1]["too_few_blocks"] is True
    assert np.isnan(rows[1]["lo"])  # no interval rather than a zero-width one


def test_verdict_gap_in_points_and_inside_outside():
    v = sp.verdict(0.5612, 0.553, 0.569)
    assert v["gap_points"] == pytest.approx(0.52) and v["theirs_inside"] is True
    v = sp.verdict(0.93, 0.92, 0.94)
    assert v["gap_points"] == pytest.approx(37.4) and v["theirs_inside"] is False


def test_hour_of_day_pools_days():
    day = 24 * H
    ts = [3 * H, 3 * H + 1, day + 3 * H, day + 5 * H]
    df = pl.DataFrame({"ts_ns": ts, "spread_ticks": [1, 2, 1, 1]})
    h = sp.by_hour_of_day(df, block=1, n_boot=50)
    three = h.filter(pl.col("hour_utc") == 3)
    assert h.height == 2 and three["n"][0] == 3 and three["days"][0] == 2
    assert three["share"][0] == pytest.approx(2 / 3)


def test_bootstrap_refuses_a_block_longer_than_the_series():
    x = sticky(5_000, 0.01)
    lo, hi = sp.block_bootstrap_ci(x, block=10_000, n_boot=200)
    assert np.isnan(lo) and np.isnan(hi)  # not a zero-width interval around the sample mean


def test_results_writes_every_b3_number(tmp_path):
    import json
    from pathlib import Path
    from plumb.results import run

    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "book.parquet"
    out = tmp_path / "results.json"
    r = run(str(sample), out, n_boot=200, synthetic=True)
    saved = json.loads(out.read_text())
    assert saved == r
    assert r["synthetic"] is True  # a sample run can never be mistaken for a result
    assert set(r["clocks"]) == {"per_state", "time_weighted", "grid_1s"}
    assert [b["block"] for b in r["blocks"]] == [100, 1000, 10000]
    assert r["verdict"]["block"] == 1000 and "gap_points" in r["verdict"]
    assert r["verdict"]["usable"] is False  # 5,000 states give only 5 blocks of 1,000
    assert {"total", "locked", "crossed", "kept", "gaps_over_1s"} <= set(r["counts"])
    assert len(r["hour_of_day"]) >= 1
