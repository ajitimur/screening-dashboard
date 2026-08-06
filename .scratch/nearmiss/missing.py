"""THROWAWAY: characterise the US candidates that have no stored bars."""
import random
import re
import sys
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
inst = parse_us_listings(_http_get(NASDAQ_LISTED_URL), _http_get(OTHER_LISTED_URL))
cands = [i for i in inst if i.role == "candidate"]
missing = [i for i in cands if i.symbol not in have]
print("candidates:", len(cands), "missing bars:", len(missing))
random.seed(0)
for i in random.sample(missing, 25):
    print(" ", i.symbol, "|", i.name[:70])
plain = re.compile(r"[A-Z]{1,5}")
print("non-plain-alpha among missing   :",
      sum(1 for i in missing if not plain.fullmatch(i.symbol)))
print("non-plain-alpha among candidates:",
      sum(1 for i in cands if not plain.fullmatch(i.symbol)))
