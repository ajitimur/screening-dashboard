"""THROWAWAY: is the missing-bars set alphabetically truncated or scattered?"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import duckdb  # noqa: E402

from screener.source import (  # noqa: E402
    NASDAQ_LISTED_URL,
    OTHER_LISTED_URL,
    _http_get,
    parse_us_listings,
)
from screener.store import Store  # noqa: E402

s = Store(duckdb.connect(str(ROOT / ".scratch/nearmiss/screener.duckdb")))
have = {
    x for (x,) in s._con.execute(
        "select distinct symbol from bars where market='US'"
    ).fetchall()
}
nl, ol = _http_get(NASDAQ_LISTED_URL), _http_get(OTHER_LISTED_URL)
inst = parse_us_listings(nl, ol)
cands = [i for i in inst if i.role == "candidate"]
n_nasdaq = 0
nasdaq_syms = {i.symbol for i in parse_us_listings(nl, ol) if i.symbol in {ln.split("|")[0] for ln in nl.splitlines()[1:-1]}}
by_letter_missing: Counter = Counter()
by_letter_all: Counter = Counter()
for i in cands:
    by_letter_all[i.symbol[0]] += 1
    if i.symbol not in have:
        by_letter_missing[i.symbol[0]] += 1
print("letter: missing/all")
for ch in sorted(by_letter_all):
    print(f"  {ch}: {by_letter_missing[ch]}/{by_letter_all[ch]}")
in_nasdaq = [i for i in cands if i.symbol in nasdaq_syms]
print("nasdaqlisted candidates:", len(in_nasdaq),
      "missing:", sum(1 for i in in_nasdaq if i.symbol not in have))
other = [i for i in cands if i.symbol not in nasdaq_syms]
print("otherlisted candidates:", len(other),
      "missing:", sum(1 for i in other if i.symbol not in have))
print("total instruments:", len(inst), "n_nasdaq parse:", n_nasdaq)
