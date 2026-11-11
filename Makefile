HOURS ?= 24
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: test sample capture replay result manifest differ report site serve

test:
	$(PY) -m pytest -q

sample:           ## synthetic data, for tests and a dry run. Never a result.
	$(PY) scripts/make_sample.py

capture:          ## record the live feed, unchanged
	$(PY) scripts/capture.py --hours $(HOURS) --out data/raw

replay:           ## raw capture to Parquet
	$(PY) -m plumb.replay data/raw/*.tsv.gz --out data/book.parquet

manifest:         ## rows for data/MANIFEST.md
	$(PY) scripts/manifest.py data/raw/*.tsv.gz data/book.parquet

result:           ## the number, three clocks, the interval
	PYTHONPATH=src $(PY) -m plumb.results data/book.parquet --out report/local/results.json

differ:           ## why-we-differ table, kept local
	PYTHONPATH=src $(PY) -m plumb.differ data/raw/*.tsv.gz --out docs/local/why_we_differ.md

report:           ## local report and figure, from the real numbers
	$(PY) scripts/plot_hourly.py data/book.parquet figures/share_by_hour.png
	$(PY) scripts/write_report.py

site:             ## private interview page: report/local/site/index.html
	$(PY) scripts/build_site.py

serve:            ## open the private page at http://127.0.0.1:8765 (this machine only)
	$(PY) -m http.server 8765 --bind 127.0.0.1 --directory report/local/site
