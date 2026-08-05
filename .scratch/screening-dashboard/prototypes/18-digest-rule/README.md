# Ticket 18 — what the digest reports under the clamped trigger

Throwaway prototype for [`18-digest-rule-under-the-clamped-trigger.md`](../../issues/18-digest-rule-under-the-clamped-trigger.md).
Runs ticket 17's split detector (`../16-trendline-fit/split.py`) over **consecutive daily bars** —
every earlier scan on this map used a 1-in-3 date grid, on which a night-over-night transition is not
expressible — and classifies each night's crossings.

**Read [`FINDINGS.md`](FINDINGS.md) first.** Short version: the fitted line can never set the trigger
(it is anchored at the cluster high and sloped ≤ 0), so the trigger *is* the cluster high; the cluster
includes today, so a detected name is never above its own level; so two of ticket 14's three crossing
buckets are unreachable rather than rare, and the digest's rule simplifies without its contents
changing.

## Code

| file | what it does |
| --- | --- |
| `crossings.py` | daily scan + the four-way crossing taxonomy; writes `out/daily.pkl`, `out/crossings.pkl` |
| `clamp.py` | recovers `cluster_high` per detection and splits every result by which term set the trigger |
| `repeats.py` | what happens to a name the night after it breaks, and how often it is reported again |
| `episodes.py` | detection episodes, breaks per episode, and what each de-duplication rule would report |
| `a3.py` | what `close_today > trigger_yesterday` means now: the k distribution and the lapsed-resumer hole |

Run order: `crossings.py` → `clamp.py` → `repeats.py` → `episodes.py` → `a3.py`. The first is the
slow one (~4 min); the rest read its pickle.

## Environment

Needs ticket 09's `cache/` (symlinked into `../09-star-score/cache`) and **pandas 3.x** — the cached
pickles carry `datetime64[s]`-backed frames that pandas 2.3 cannot unpickle. `venv/` here is built for
it:

```
python3.11 -m venv venv && ./venv/bin/pip install "pandas==3.0.5" "numpy==2.4.6"
./venv/bin/python crossings.py
```

## Caveats

- Ticket 08's **D15 decile gate is not applied**, so every rows-per-night figure is an upper bound.
- Volumes are scaled from the sample to ticket 05's 1,966 US / 288 IDX universes.
- `crossings.py`'s "where does the trigger come from now?" line is a placeholder that always prints
  100%; `clamp.py` is what actually measures it.
