# Ticket 26 — the line penalty and the longer list

Throwaway working for [`26-the-line-penalty-and-the-longer-list.md`](../../issues/26-the-line-penalty-and-the-longer-list.md).
**Read [`FINDINGS.md`](FINDINGS.md) first.**

No new grading. Ticket 26 was a grilling ticket and every number here is recomputed from evidence
that already existed: deck F's 105 grades, ticket 15's published rubric, ticket 25's `split.pkl`
scan, and ticket 18's cached consecutive-bar scan.

| file | what it does |
| --- | --- |
| `deckF_machine.py` | scores deck F's three arms with ticket 15 R4's thresholds — the machine's view of cards only the eye had seen |
| `nightly_mix.py` | the merged nightly list: length (both scales), star distribution, and the top of ticket 11's sort |
| `digest_volume.py` | ticket 18's classifier re-run with the line test as a switch |

Run order is free; nothing depends on anything else here.

```
./deckF_machine.py F=342443144532212342111434311434253524334334252443334444223325421431224312222223244354422234245233422234221
./nightly_mix.py nights=250
./digest_volume.py
```

## Environment

Needs ticket 09's `cache/` symlinked into `../09-star-score/cache` and **pandas 3.x** (the cached
pickles carry `datetime64[s]`-backed frames that pandas 2.3 cannot unpickle). `digest_volume.py`
also needs ticket 18's `out/daily.pkl`; it looks locally first and falls back to the ticket-18
worktree.

## Caveats

- The scan pool is **628 US names** — a random Nasdaq draw plus a 39-name momentum core — not ticket
  05's 1,966-name liquidity-gated universe. `nightly_mix.py` prints both the raw sample count and the
  ×3.13 rescale, and says which convention each earlier ticket used. See FINDINGS §5.
- `digest_volume.py` inherits ticket 18's caveat: D15's decile gate is not applied to its scan, so
  its rows-per-night figures are upper bounds. The **ratio** between the two gate sets is the
  answer; the levels are ticket 18's.
- Sub-test splits are n=8/n=9 and were pre-registered as descriptive only. Nothing here re-opens
  that.
