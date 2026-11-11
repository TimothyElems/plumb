"""b5: the report puts the result first, refuses synthetic numbers, and keeps its tone."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "book.parquet"
BANNED = re.compile(r"they\s+(are|were)\s+wrong|\bincorrect\b|\bdebunk|false claim|\bmisleading\b|\bbogus\b", re.I)


def fake_results(synthetic=False):
    from plumb.results import run
    r = run(str(SAMPLE), None, n_boot=200, synthetic=True)
    r["synthetic"] = synthetic
    r["verdict"]["usable"] = True
    return r


def fake_differ():
    from plumb.differ import build
    return build([ROOT / "data" / "sample" / "synthetic_raw.tsv.gz"], max_hours=1.0)


def test_report_refuses_synthetic_numbers():
    from scripts_write_report import render
    with pytest.raises(ValueError, match="synthetic"):
        render(fake_results(synthetic=True), fake_differ())


def test_result_line_comes_first_and_states_gap_and_verdict():
    from scripts_write_report import render
    md = render(fake_results(), fake_differ())
    first = [l for l in md.splitlines() if l.strip() and not l.startswith("#")][0]
    assert first.startswith("**Result:** I measured")
    assert "55.60%" in first and "points" in first and ("did not match" in first or "matched" in first)


def test_report_states_every_limit():
    from scripts_write_report import render
    md = render(fake_results(), fake_differ()).lower()
    for limit in ("one venue", "my own recording period", "one clock family", "batched", "never saw their data"):
        assert limit in md, limit


@pytest.mark.parametrize("path", ["report/report.md", "README.md", "docs/why_we_differ.md"])
def test_public_files_keep_the_tone(path):
    assert not BANNED.search((ROOT / path).read_text())


def test_generated_report_keeps_the_tone():
    from scripts_write_report import render
    assert not BANNED.search(render(fake_results(), fake_differ()))


def test_figure_is_by_hour_of_day_with_their_line(tmp_path):
    from scripts_plot_hourly import main
    out = tmp_path / "fig.png"
    data = main(str(SAMPLE), str(out), block=100)
    assert out.stat().st_size > 5000
    assert "days" in data.columns  # pooled by hour of day, not by capture hour
