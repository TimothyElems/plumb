# Plumb

**Result:** I re-measured HFT Architecture's "55.60% of BTC-USD book states have a one-tick spread" on my own ~4-day Coinbase recording, against a match rule committed before any data. The number stays local, because Coinbase's terms bar showing derived data; method, limits and reasons for any gap: [report/report.md](report/report.md).

Their wording and my assumptions: [docs/definitions.md](docs/definitions.md). Match rule: [docs/match-rule.md](docs/match-rule.md). Data and hashes: [data/MANIFEST.md](data/MANIFEST.md).

## Run it

```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,plot]"
make test                      # tests run on the synthetic sample only
make capture HOURS=96          # record the live feed into data/raw/ (leave it running)
make replay manifest result differ report site
make serve                     # open http://127.0.0.1:8765
```

`make site` builds a one-page summary at `report/local/site/index.html`: the result, why it differs from 55.60%, and the share by hour. It runs only on your machine and is meant for screen sharing, never for deploying or sending. Under 72 hours of data it is labelled partial. `data/sample` is synthetic and never a result. Raw data and everything derived from it stay out of git.
