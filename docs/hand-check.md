# Hand check

**Result: 10 of 10 states match, and an independent replay agrees on 962 of 962 states.** Checked 2026-11-10.

The table of states (prices and spreads) is kept on my machine in `docs/local/`, not in this repo. It is computed
from Coinbase market data, and Coinbase's Market Data Terms do not allow showing works derived from it to third parties.
Anyone can produce their own table with the steps below.

**Data.** A 60-second trial capture recorded with `scripts/capture.py`, separate from the main capture and not part of any
result: `btcusd_level2_batch_20261110T08.tsv.gz`, sha256 `11e97b5b26c5a4e40dce6eef5f5f762ba2169687a7eb74bce402043df1f72280`,
1 snapshot (about 39,000 levels) and 962 updates.

**Method.** A book that size cannot be rebuilt on paper. `scripts/hand_check.py` rebuilds it a second way, sharing no code
with `plumb.replay`: prices stay `Decimal`, and best bid and best ask are plain `max()` and `min()` over the price keys. It
compares every state with the Parquet file, then prints 10 of them with the subtraction written out, plus the raw change
that set the top of the book in that message, so each can be redone by hand. The 10 cover the first state after the snapshot,
the widest spread in the file, a range of wide spreads, and ordinary 1-tick states.

Run: `python scripts/hand_check.py RAW.tsv.gz BOOK.parquet`

**What it showed about method.** Wide spreads (hundreds of ticks) occur in a full-depth book too, so the depth-five
reconstruction cannot be assumed to be the only source of wide states. The why-we-differ table measures it.
