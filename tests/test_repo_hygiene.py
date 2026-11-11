"""b6: raw market data never enters git; only the manifest does."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return out.splitlines()


def test_no_raw_or_derived_market_data_is_tracked():
    bad = [f for f in tracked() if f.startswith(("data/raw/", "data/source/", "docs/local/", "report/local/", "figures/"))
           or f == "data/book.parquet" or (f.endswith(".tsv.gz") and not f.startswith("data/sample/"))]
    assert bad == [], bad


def test_manifest_is_tracked():
    assert "data/MANIFEST.md" in tracked()
