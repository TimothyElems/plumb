"""One figure for the report: share by hour of day (pooled across days), its interval, and their number as a line.

Needs matplotlib (pip install -e ".[plot]"). Run: python scripts/plot_hourly.py data/book.parquet
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from plumb import spread as sp  # noqa: E402

THEIRS = 55.60


def main(path: str, out: str = "figures/share_by_hour.png", block: int = 1000):
    """Draws the figure and returns the table it was drawn from. figures/ is gitignored: it is derived data."""
    kept, _ = sp.clean(sp.load(path))
    h = sp.by_hour_of_day(kept, block=block)
    x = list(range(h.height))
    share, lo, hi = (h[c].to_numpy() * 100 for c in ("share", "lo", "hi"))
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=160)
    ax.fill_between(x, lo, hi, color="#2f5d8c", alpha=0.18, linewidth=0)
    ax.plot(x, share, color="#2f5d8c", linewidth=2)
    ax.axhline(THEIRS, color="#7d5e00", linewidth=1.5, linestyle="--")
    ax.text(len(x) - 1, THEIRS, " their 55.60", color="#7d5e00", va="bottom", ha="right", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(v):02d}" for v in h["hour_utc"].to_list()], fontsize=8)
    ax.set_xlabel("hour of day, UTC")
    ax.set_ylabel("share of states with 1-tick spread (%)")
    ax.set_title(f"Share by hour of day, 95% block-bootstrap band (block {block})", loc="left", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#d5d9d6", linewidth=0.6)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out)
    print(f"wrote {out}")
    return h


if __name__ == "__main__":
    main(sys.argv[1], *(sys.argv[2:3]))
