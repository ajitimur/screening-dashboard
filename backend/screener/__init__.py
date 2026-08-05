"""Qullamaggie screening dashboard backend.

Walking skeleton (ticket 27): the DuckDB store, the run record and the read API
behind the two market tabs. The store discipline established here — dated,
append-only rows keyed ``(market, session, ...)``, written once and never
rewritten — is the prefactor every later ticket depends on (v1-spec §7.2).
"""

MARKETS = ("IDX", "US")
