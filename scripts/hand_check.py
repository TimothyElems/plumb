"""Independent check: no code from plumb.replay. Prices stay Decimal strings, best = max/min over keys."""
import gzip, json, sys
from decimal import Decimal
import polars as pl

raw, pq = sys.argv[1], sys.argv[2]
bids, asks, states = {}, {}, []
with gzip.open(raw, "rt") as f:
    for line in f:
        recv, msg = line.rstrip("\n").split("\t", 1)
        m = json.loads(msg)
        if m["type"] == "snapshot":
            bids = {Decimal(p): s for p, s in m["bids"] if Decimal(s) != 0}
            asks = {Decimal(p): s for p, s in m["asks"] if Decimal(s) != 0}
        elif m["type"] == "l2update":
            for side, p, s in m["changes"]:
                book = bids if side == "buy" else asks
                if Decimal(s) == 0: book.pop(Decimal(p), None)
                else: book[Decimal(p)] = s
            b, a = max(bids), min(asks)
            touched = [c for c in m["changes"] if Decimal(c[1]) in (b, a)]
            states.append((m["time"], b, a, touched, len(m["changes"])))
df = pl.read_parquet(pq).with_columns(sp=pl.col("ask_tick") - pl.col("bid_tick"))
assert len(states) == df.height, (len(states), df.height)
# 10 states: the first, the widest, and others spread across spreads; prefer ones whose top was set in that message
idx = [0, int(df["sp"].arg_max())]
for want in sorted(set(df["sp"].to_list()), reverse=True):
    for i, st in enumerate(states):
        if len(idx) >= 7: break
        if df["sp"][i] == want and st[3] and i not in idx: idx.append(i); break
idx += [i for i, st in enumerate(states) if df["sp"][i] == 1 and st[3] and i not in idx][: 10 - len(idx)]
print("| # | exchange time | best bid | best ask | spread by hand (ticks) | by script | match | top price set in this message |")
print("|---|---|---|---|---|---|---|---|")
ok = 0
for k, i in enumerate(sorted(idx), 1):
    t, b, a, touched, n = states[i]
    hand = (a - b) / Decimal("0.01")
    script = df["sp"][i]
    match = hand == script and df["bid_tick"][i] == int(b * 100) and df["ask_tick"][i] == int(a * 100)
    ok += match
    print(f"| {k} | {t} | {b} | {a} | ({a} − {b}) / 0.01 = {hand} | {script} | {'yes' if match else 'NO'} | "
          + ", ".join(f"{s} {p} → {q}" for s, p, q in touched) + " |")
print(f"\n{ok}/10 match. Full independent replay agrees on {sum(int(df['bid_tick'][i]) == int(states[i][1]*100) and int(df['ask_tick'][i]) == int(states[i][2]*100) for i in range(df.height))}/{df.height} states.")
