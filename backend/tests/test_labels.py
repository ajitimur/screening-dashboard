"""Seam 6: the sector/industry label cache and its policy (spec §3.1, §3.3,
§7.4 stage 7).

Every universe member carries a sector and an industry, both arriving in the
*same* source request (spec §3.1) — which is what makes industry the theme layer
for free (§4.4). A label costs one request per symbol, so the cache is the one
incremental piece of the pipeline (§3.3), governed by three rules:

- **New names block** — a member with no cached label is fetched before it can
  appear (a name with no industry cannot be placed on the axis).
- **Existing names roll** — ~1/30th of the cached members refresh nightly,
  stalest first, so staleness is bounded and nightly cost does not grow with the
  universe.
- **A failed fetch never nulls a cached value** — silence leaves yesterday's
  label in place and reschedules the fetch.

The source boundary is faked (Yahoo fails as silence, §3.2); no test touches the
network.
"""

from datetime import date, timedelta

from screener.labels import SLICE, Label, select_fetches
from screener.pipeline import refresh_labels
from screener.source import RateLimitedError, Source
from screener.store import Store


# -- an injected clock: sleeps advance virtual time (as in Seam 3) ------------


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


# -- a fake source client that also serves .info ------------------------------


class FakeInfoClient:
    """Fakes ``fetch_info``: maps a symbol to successive outcomes, so a name can
    be silent then resolve on a retry. ``"429"`` raises; a dict is returned."""

    def __init__(self, responses=None) -> None:
        self._responses = responses or {}
        self.info_calls: list[str] = []

    def enumerate(self, market):  # unused here, present for the protocol
        return []

    def fetch(self, symbol, start=None):  # unused here
        return []

    def fetch_info(self, symbol):
        self.info_calls.append(symbol)
        outcomes = self._responses.get(symbol, [{}])
        seen = self.info_calls.count(symbol) - 1
        outcome = outcomes[min(seen, len(outcomes) - 1)]
        if outcome == "429":
            raise RateLimitedError(symbol)
        return outcome


def make_source(client):
    clock = FakeClock()
    src = Source(
        client, rate_per_sec=12, max_attempts=4, backoff_base=1.0,
        monotonic=clock.monotonic, sleep=clock.sleep,
    )
    return src, clock


def _label(symbol, as_of, sector="Tech", industry="Software"):
    return Label(symbol=symbol, sector=sector, industry=industry, as_of=as_of)


# == the pure policy: select_fetches ==========================================


def test_new_names_all_block_and_are_selected():
    # Every member absent from the cache is a "new" fetch — none are skipped.
    members = ["A", "B", "C"]
    new, refresh = select_fetches(members, cached={})
    assert set(new) == {"A", "B", "C"}
    assert refresh == []


def test_existing_names_refresh_a_thirtieth_slice_stalest_first():
    # 60 cached members -> ceil(60/30) = 2 refresh per night, and the two picked
    # are the stalest by as_of (with symbol as the tiebreaker).
    cached = {f"S{i}": _label(f"S{i}", date(2026, 8, 4)) for i in range(60)}
    cached["S3"] = _label("S3", date(2026, 7, 1))   # stalest
    cached["S9"] = _label("S9", date(2026, 7, 2))   # next stalest
    members = [f"S{i}" for i in range(60)]

    new, refresh = select_fetches(members, cached)

    assert new == []
    assert refresh == ["S3", "S9"]


def test_nightly_refresh_cost_does_not_grow_with_the_universe():
    # A fully-warm universe refreshes only its 1/30th slice, never all of it —
    # this is the "flat nightly cost" property: 900 cached names cost 30 fetches,
    # not 900. Old members are not re-fetched every night.
    for size in (30, 300, 900):
        cached = {f"S{i}": _label(f"S{i}", date(2026, 8, 4)) for i in range(size)}
        members = list(cached)
        _new, refresh = select_fetches(members, cached)
        assert len(refresh) == size // SLICE
        assert len(refresh) < size  # bounded well below a full pass


def test_rolling_refresh_covers_every_name_within_slice_nights():
    # Starting all-equally-stale, the stalest-first rule cycles through the whole
    # cache in SLICE nights: every name is refreshed at least once, none missed.
    size = 90
    cached = {f"S{i:02d}": _label(f"S{i:02d}", date(2026, 8, 4)) for i in range(size)}
    members = list(cached)
    seen: set[str] = set()
    day = date(2026, 8, 5)
    for _ in range(SLICE):
        _new, refresh = select_fetches(members, cached)
        assert len(refresh) == size // SLICE
        for s in refresh:
            cached[s] = _label(s, day)  # refreshed today -> now the freshest
            seen.add(s)
        day += timedelta(days=1)
    assert seen == set(members)  # full turnover within a month


# == the source: resolve_labels ===============================================


def test_resolve_labels_returns_both_labels_from_one_request():
    client = FakeInfoClient(
        responses={"AAA": [{"sector": "Technology", "industry": "Semiconductors"}]}
    )
    src, _ = make_source(client)

    res = src.resolve_labels("AAA")

    assert res.status == "resolved"
    assert res.sector == "Technology"
    assert res.industry == "Semiconductors"
    assert client.info_calls == ["AAA"]  # one request carries both


def test_resolve_labels_silence_is_unresolved_and_retried():
    client = FakeInfoClient(responses={"DEAD": [{}]})  # silence, always
    src, _ = make_source(client)

    res = src.resolve_labels("DEAD")

    assert res.status == "unresolved"
    assert res.sector == "" and res.industry == ""
    assert client.info_calls == ["DEAD"] * 4  # retried up to max_attempts


def test_resolve_labels_backs_off_on_429_then_resolves():
    client = FakeInfoClient(
        responses={"AAA": ["429", "429", {"sector": "Energy", "industry": "Coal"}]}
    )
    src, clock = make_source(client)

    res = src.resolve_labels("AAA")

    assert res.status == "resolved"
    assert 1.0 in clock.slept and 2.0 in clock.slept  # exponential backoff


def test_resolve_labels_missing_industry_is_unresolved():
    # A name with a sector but no industry cannot be placed on the axis, so a
    # partial result is treated as silence — not half-cached.
    client = FakeInfoClient(responses={"HALF": [{"sector": "Technology"}]})
    src, _ = make_source(client)

    assert src.resolve_labels("HALF").status == "unresolved"


# == the store: the incremental cache =========================================


def test_store_upserts_and_reads_a_label(store: Store):
    store.upsert_label("US", "AAA", "Technology", "Software", date(2026, 8, 5))
    got = store.label("US", "AAA")
    assert got == Label("AAA", "Technology", "Software", date(2026, 8, 5))
    assert store.labels("US") == {"AAA": got}


def test_store_label_upsert_is_in_place_not_append(store: Store):
    # Unlike the append-only dated tables, the label cache is overwritten in
    # place (spec §3.3): a second upsert replaces, never duplicates.
    store.upsert_label("US", "AAA", "Technology", "Software", date(2026, 8, 4))
    store.upsert_label("US", "AAA", "Healthcare", "Biotech", date(2026, 8, 5))
    assert store.label("US", "AAA") == Label(
        "AAA", "Healthcare", "Biotech", date(2026, 8, 5)
    )
    assert len(store.labels("US")) == 1


def test_store_labels_are_per_market(store: Store):
    store.upsert_label("US", "AAA", "Technology", "Software", date(2026, 8, 5))
    store.upsert_label("IDX", "BBB.JK", "Energy", "Coal", date(2026, 8, 5))
    assert set(store.labels("US")) == {"AAA"}
    assert set(store.labels("IDX")) == {"BBB.JK"}


# == the pipeline stage: refresh_labels =======================================


def test_new_member_is_fetched_before_it_appears(store: Store):
    client = FakeInfoClient(
        responses={"NEW": [{"sector": "Technology", "industry": "Software"}]}
    )
    src, _ = make_source(client)

    labeled = refresh_labels(store, src, "US", ["NEW"], date(2026, 8, 5))

    assert "NEW" in labeled  # it carries a label, so it may appear
    assert store.label("US", "NEW").sector == "Technology"


def test_new_member_with_failed_fetch_does_not_appear_and_retries(store: Store):
    client = FakeInfoClient(responses={"SHY": [{}]})  # silence
    src, _ = make_source(client)

    labeled = refresh_labels(store, src, "US", ["SHY"], date(2026, 8, 5))

    assert "SHY" not in labeled            # blocked: no label, cannot appear
    assert store.label("US", "SHY") is None  # nothing cached
    # Next night it is still "new" and blocks again (the implicit retry).
    _new, _refresh = select_fetches(["SHY"], store.labels("US"))
    assert "SHY" in _new


def test_failed_refresh_leaves_the_cached_value_intact(store: Store):
    # A cached name whose refresh comes back silent keeps yesterday's label and
    # is retried — the label cache's version of sticky membership (§3.4 rule 6).
    store.upsert_label("US", "OLD", "Technology", "Software", date(2026, 7, 1))
    client = FakeInfoClient(responses={"OLD": [{}]})  # refresh fails
    src, _ = make_source(client)

    refresh_labels(store, src, "US", ["OLD"], date(2026, 8, 5))

    kept = store.label("US", "OLD")
    assert kept == Label("OLD", "Technology", "Software", date(2026, 7, 1))
    # as_of did not move, so it stays the stalest and is retried next night.
    _new, refresh = select_fetches(["OLD"], store.labels("US"))
    assert refresh == ["OLD"]


def test_refresh_rolls_only_a_slice_of_cached_members(store: Store):
    # 60 already-cached members -> only 2 (ceil(60/30)) are re-fetched tonight;
    # nightly cost is bounded regardless of universe size.
    for i in range(60):
        store.upsert_label("US", f"S{i}", "Technology", "Software", date(2026, 8, 4))
    client = FakeInfoClient(
        responses={f"S{i}": [{"sector": "Energy", "industry": "Coal"}] for i in range(60)}
    )
    src, _ = make_source(client)

    refresh_labels(store, src, "US", [f"S{i}" for i in range(60)], date(2026, 8, 5))

    assert len(client.info_calls) == 2  # a 1/30th slice, not 60


def test_coverage_new_names_blocked_existing_kept(store: Store):
    # 100 members: 99 already cached (only ~3 refresh tonight, the rest keep
    # their cached label), 1 brand new and fetched. All 100 carry both labels ->
    # ≥99% coverage, and the cost is 1 new + ceil(99/30)=4 refresh = 5 fetches.
    for i in range(99):
        store.upsert_label("US", f"S{i}", "Technology", "Software", date(2026, 8, 4))
    members = [f"S{i}" for i in range(99)] + ["NEW"]
    responses = {"NEW": [{"sector": "Energy", "industry": "Coal"}]}
    responses.update(
        {f"S{i}": [{"sector": "Technology", "industry": "Software"}] for i in range(99)}
    )
    client = FakeInfoClient(responses=responses)
    src, _ = make_source(client)

    labeled = refresh_labels(store, src, "US", members, date(2026, 8, 5))

    assert labeled == set(members)                 # 100% carry both labels
    assert len(client.info_calls) == 1 + 4         # 1 new + a 1/30th slice
