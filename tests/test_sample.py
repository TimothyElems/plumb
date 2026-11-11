from pathlib import Path

from plumb import spread as sp

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "book.parquet"


def test_sample_runs_end_to_end():
    s = sp.summary(sp.load(str(SAMPLE)), block=200)
    assert s["total"] == 5000 and s["crossed"] == 0
    assert 0.0 < s["ci_lo"] < s["per_event"] < s["ci_hi"] < 1.0
