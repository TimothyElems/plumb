"""Share of book states with spread == 1 tick: three clocks, gaps, hourly view, block bootstrap."""
from __future__ import annotations

import numpy as np
import polars as pl


CAP_NS = 10_000_000_000  # one state never counts for more than 10 s of clock time (definitions A8)


def load(path: str) -> pl.DataFrame:
    """Needs ts_ns (Int64, exchange time), bid_tick, ask_tick (Int64). Sorted by time, ties kept in file order."""
    return (pl.read_parquet(path).sort("ts_ns", maintain_order=True)
            .with_columns(spread_ticks=pl.col("ask_tick") - pl.col("bid_tick")))


def add_durations(df: pl.DataFrame, cap_ns: int = CAP_NS) -> pl.DataFrame:
    """How long each state lasted, measured on the FULL series before anything is dropped.

    If durations were computed after dropping locked or crossed rows, their time would be
    credited to the state before them. The last state has no known duration (null)."""
    return df.with_columns(dt=(pl.col("ts_ns").shift(-1) - pl.col("ts_ns")).clip(0, cap_ns))


def clean(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Locked (0) and crossed (<0) books are a stated choice. Count them, never hide them."""
    locked = df.filter(pl.col("spread_ticks") == 0).height
    crossed = df.filter(pl.col("spread_ticks") < 0).height
    kept = df.filter(pl.col("spread_ticks") >= 1)
    return kept, {"locked": locked, "crossed": crossed, "kept": kept.height, "total": df.height}


def share_per_event(df: pl.DataFrame) -> float:
    return df.select((pl.col("spread_ticks") == 1).mean()).item()


def share_time_weighted(df: pl.DataFrame, cap_ns: int = CAP_NS) -> float:
    """Weight each state by how long it lasted. Cap long gaps so an outage cannot dominate.

    Uses a `dt` column if present (from add_durations on the full series), else computes one."""
    d = (df if "dt" in df.columns else add_durations(df, cap_ns)).drop_nulls("dt")
    total = d["dt"].sum()
    if total == 0:
        return float("nan")
    return d.select(((pl.col("spread_ticks") == 1).cast(pl.Float64) * pl.col("dt")).sum()).item() / total


def share_on_grid(df: pl.DataFrame, step_ns: int = 1_000_000_000, cap_ns: int = CAP_NS, keep_bad: bool = False) -> float:
    """Last known state at each grid time. Backward as-of only, so no future state leaks in.

    Pass the FULL series. A grid point is left out if its state is locked or crossed, or older
    than cap_ns (a hole in the feed), so neither is read as the state before it."""
    t0, t1 = df["ts_ns"].min(), df["ts_ns"].max()
    grid = pl.DataFrame({"ts_ns": np.arange(t0, t1, step_ns, dtype=np.int64)})
    states = df.select("ts_ns", "spread_ticks").with_columns(state_ns=pl.col("ts_ns"))
    j = (grid.join_asof(states, on="ts_ns", strategy="backward").drop_nulls()
         .filter((pl.col("ts_ns") - pl.col("state_ns") <= cap_ns) & ((pl.col("spread_ticks") >= 1) | keep_bad)))
    return j.select((pl.col("spread_ticks") == 1).mean()).item()


def gaps(df: pl.DataFrame, threshold_ns: int = 1_000_000_000) -> pl.DataFrame:
    """Holes in the feed longer than the threshold. Report them in the manifest."""
    return (df.select("ts_ns").with_columns(prev=pl.col("ts_ns").shift(1))
            .with_columns(gap_ns=pl.col("ts_ns") - pl.col("prev"))
            .filter(pl.col("gap_ns") > threshold_ns)
            .select(start_ns="prev", end_ns="ts_ns", gap_ns="gap_ns"))


def block_bootstrap_ci(indicator: np.ndarray, block: int = 1000, n_boot: int = 2000, seed: int = 7,
                       level: float = 0.95) -> tuple[float, float]:
    """Moving-block bootstrap of the mean of a 0/1 series.

    Neighbouring states are correlated, so plain resampling gives an interval that is too narrow.
    Vectorised through block sums, so it stays fast on millions of rows.
    """
    x = np.asarray(indicator, dtype=np.float64)
    n = len(x)
    block = max(1, block)
    if n == 0 or block > n:
        # One block (or none) cannot show any variation: return no interval, not a zero-width one.
        return float("nan"), float("nan")
    cs = np.concatenate([[0.0], np.cumsum(x)])
    sums = cs[block:] - cs[:-block]  # sum of every window of length `block`
    n_blocks = max(1, n // block)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    step = max(1, 20_000_000 // n_blocks)  # keep memory bounded
    for i in range(0, n_boot, step):
        m = min(step, n_boot - i)
        starts = rng.integers(0, len(sums), size=(m, n_blocks))
        means[i:i + m] = sums[starts].sum(axis=1) / (n_blocks * block)
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))


THEIRS = 0.5560
MIN_BLOCKS = 20  # below this, an interval mostly reflects which few blocks were drawn


def block_sweep(indicator: np.ndarray, blocks=(100, 1000, 10000), n_boot: int = 2000, seed: int = 7) -> list[dict]:
    """The same interval at several block lengths, with a flag when too few blocks fit."""
    x = np.asarray(indicator, dtype=np.float64)
    out = []
    for b in blocks:
        lo, hi = block_bootstrap_ci(x, block=b, n_boot=n_boot, seed=seed)
        nb = len(x) // b
        out.append({"block": b, "n_blocks": nb, "lo": lo, "hi": hi, "width": hi - lo,
                    "too_few_blocks": nb < MIN_BLOCKS})
    return out


def interval_grows(rows: list[dict], factor: float = 1.5) -> bool:
    """True if the widest usable interval is more than `factor` times the narrowest.

    Growth with block length means neighbouring states are correlated over long stretches, so the
    short-block interval is too narrow. Say so in the report."""
    w = [r["width"] for r in rows if not r["too_few_blocks"] and np.isfinite(r["width"])]
    return len(w) >= 2 and max(w) > factor * min(w)


def verdict(share: float, lo: float, hi: float, theirs: float = THEIRS) -> dict:
    """The match rule (docs/match-rule.md): their number inside my interval or not, and the gap in points."""
    return {"share": share, "lo": lo, "hi": hi, "theirs": theirs,
            "gap_points": round((share - theirs) * 100, 4), "theirs_inside": bool(lo <= theirs <= hi)}


def by_hour_of_day(df: pl.DataFrame, block: int = 1000, n_boot: int = 1000) -> pl.DataFrame:
    """Share per UTC hour of day, pooling the same hour across days, with a block-bootstrap interval.

    Rows are kept in time order inside each hour, so blocks stay runs of neighbouring states."""
    d = df.with_columns(hour_utc=((pl.col("ts_ns") // 3_600_000_000_000) % 24).cast(pl.Int32),
                        day=pl.col("ts_ns") // 86_400_000_000_000)
    out = []
    for (h,), g in d.sort("ts_ns").group_by("hour_utc", maintain_order=True):
        ind = (g["spread_ticks"] == 1).to_numpy()
        lo, hi = block_bootstrap_ci(ind, block=block, n_boot=n_boot)
        out.append({"hour_utc": int(h), "n": g.height, "days": g["day"].n_unique(), "share": float(ind.mean()),
                    "lo": lo, "hi": hi})
    return pl.DataFrame(out).sort("hour_utc")


def hourly(df: pl.DataFrame, block: int = 1000, n_boot: int = 1000) -> pl.DataFrame:
    """Share and interval per UTC hour of the capture. Shows whether the period matters."""
    d = df.with_columns(hour=(pl.col("ts_ns") // 3_600_000_000_000))
    out = []
    for (h,), g in d.group_by("hour", maintain_order=True):
        ind = (g["spread_ticks"] == 1).to_numpy()
        lo, hi = block_bootstrap_ci(ind, block=block, n_boot=n_boot)
        out.append({"hour_utc": int(h) % 24, "hour_index": int(h), "n": g.height, "share": float(ind.mean()), "lo": lo, "hi": hi})
    return pl.DataFrame(out)


def summary(df: pl.DataFrame, block: int = 1000) -> dict:
    full = add_durations(df)
    kept, info = clean(full)
    ind = (kept["spread_ticks"] == 1).to_numpy()
    lo, hi = block_bootstrap_ci(ind, block=block)
    return {**info, "per_event": share_per_event(kept), "time_weighted": share_time_weighted(kept),
            "grid_1s": share_on_grid(full), "ci_lo": lo, "ci_hi": hi, "block": block}


if __name__ == "__main__":
    import sys

    s = summary(load(sys.argv[1]))
    print({k: s[k] for k in ("total", "locked", "crossed", "kept")})
    print(f"per event      {s['per_event']:.4%}")
    print(f"time weighted  {s['time_weighted']:.4%}")
    print(f"1 s grid       {s['grid_1s']:.4%}")
    print(f"95% block-bootstrap CI (per event, block {s['block']}): [{s['ci_lo']:.4%}, {s['ci_hi']:.4%}]   theirs 55.60%")
