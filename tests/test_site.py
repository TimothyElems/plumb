"""The local interview page: essentials only, real numbers only, labelled when partial, never inside git."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
from test_report import BANNED, fake_differ, fake_results  # noqa: E402


def data_of(html):
    return json.loads(re.search(r'<script id="plumb-data" type="application/json">(.*?)</script>', html, re.S).group(1))


def visible_text(html):
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def test_site_refuses_synthetic_numbers():
    from scripts_build_site import render
    with pytest.raises(ValueError, match="synthetic"):
        render(fake_results(synthetic=True), fake_differ())


def test_answer_comes_first_with_number_theirs_and_verdict():
    from scripts_build_site import render
    r = fake_results()
    text = visible_text(render(r, fake_differ()))
    first = text[: text.index("Why")]
    assert f"{100 * r['verdict']['share']:.1f}%" in first and "55.6" in first
    assert ("Matched" in first) or ("Did not match" in first)


def test_bridge_goes_from_mine_to_theirs_through_the_two_largest_factors():
    from scripts_build_site import bridge
    w = fake_differ()
    steps = bridge(fake_results(), w)
    assert steps[0]["label"].startswith("My measurement") and steps[-1]["label"].startswith("Their")
    pair = w["combined"] if w["combined"]["value"] is not None else w["combined"]["fallback"]
    assert steps[-2]["value"] == pytest.approx(pair["value"])
    assert len(steps) == 4


def test_page_is_short():
    from scripts_build_site import render
    text = visible_text(render(fake_results(), fake_differ()))
    assert len(text.split()) < 170, len(text.split())
    for gone in ("Interval by block length", "Their words, my choices", "Locked / crossed", "Time-weighted"):
        assert gone not in text


def test_limits_in_one_line_and_tone():
    from scripts_build_site import render
    html = render(fake_results(), fake_differ())
    assert re.search(r"One venue.*batched feed.*their data", visible_text(html))
    assert not BANNED.search(html)


def test_partial_capture_is_labelled():
    from scripts_build_site import render
    assert 'class="partial"' in render(fake_results(), fake_differ())


def test_full_capture_has_no_partial_label():
    from scripts_build_site import render
    r = fake_results()
    r["last_ts_ns"] = r["first_ts_ns"] + 96 * 3_600_000_000_000
    assert 'class="partial"' not in render(r, fake_differ())


def test_default_output_is_gitignored():
    import subprocess
    from scripts_build_site import OUT
    rel = OUT.relative_to(ROOT)
    assert subprocess.run(["git", "check-ignore", "-q", str(rel)], cwd=ROOT).returncode == 0
