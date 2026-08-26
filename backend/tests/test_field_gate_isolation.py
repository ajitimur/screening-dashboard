"""#211's gate isolation: the fast path must be the classifier, and a dropped gate
must only ever admit.

:mod:`backtest.field_gate_isolation` exists to answer one question — *which* of the
stateless universe's three gates reverses the rubric's edge — and it can only answer
it if its rebuilt membership is the run's own membership. Two things therefore have
to hold, and both are pinned here rather than assumed:

- **Its gates are :mod:`backtest.universe`'s gates.** The module holds each
  candidate's bars as parallel lists and indexes them per session instead of
  re-slicing the symbol's history, and it carries its own copy of the app's private
  ``_median``. These tests put both against the originals on the same bars and
  require the same answer, so neither can drift from what it stands in for.
- **Every variant reads one shared evaluation of the gates.** The predicates do not
  depend on the variant, so they are computed once and each variant is a boolean
  ``and`` over the same flags. That batch path must agree with the direct one, or
  "only the gate set moved" stops being true.
- **Dropping a gate widens the field and never moves a constant.** A variant is
  the run's gates *minus one*, so its membership must be a superset of the
  baseline's. A variant that narrowed the field, or that passed a name the
  remaining gates reject, would not be isolating a gate at all.

The store-backed half of the claim — that the full-gate rebuild reproduces
``backtest.duckdb``'s own universe rows exactly — is checked against the real store
by :func:`~backtest.field_gate_isolation.verify_reconstruction` on every run, and
recorded in ``references/backtest_gate_isolation.txt``. What is tested here is the
arithmetic that check relies on.
"""

from datetime import date, timedelta

import pytest

from screener.bars import Bar
from screener.store import Store
from screener.universe import median_dollar_volume

from backtest.contract import DEFAULT_CONTRACT, UNIVERSE_LIQUIDITY_FLOOR_KEY
from backtest.universe import (
    ADR_FLOOR,
    Candidate,
    is_member as classifier_is_member,
    passes_adr_gate,
    passes_liquidity_gate,
    passes_trend_gate,
)
from backtest.field_gate_isolation import (
    ADR,
    ALL_GATES,
    LIQUIDITY,
    TREND,
    VARIANTS,
    GateVariant,
    ReconstructionFailed,
    _median,
    gate_flags_by_session,
    members_at,
    memberships_under,
    run_isolation,
    series_of,
)

US_FLOOR = DEFAULT_CONTRACT.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)["US"]

# 60 bars through t−1 plus the signal session itself, so every case can be asked
# both "what was knowable the night before" and "does day t's own bar leak".
SESSIONS = [date(2020, 1, 1) + timedelta(days=i) for i in range(61)]
SIGNAL = SESSIONS[-1]


def _bars(
    *,
    price: float = 50.0,
    drift: float = 0.002,
    adr_pct: float = 0.05,
    dollar_volume: float = 50_000_000.0,
    sessions: list[date] | None = None,
) -> list[Bar]:
    """Bars that clear every gate by default, one knob per gate."""
    out = []
    for i, s in enumerate(sessions or SESSIONS):
        p = price * (1 + drift) ** i
        out.append(
            Bar(
                session=s,
                open=p,
                high=p * (1 + adr_pct),
                low=p,
                close=p,
                adj_close=p,
                volume=max(1, round(dollar_volume / p)),
            )
        )
    return out


def _series(symbol="AAA", **kwargs):
    return series_of(symbol, _bars(**kwargs))


def _k(series, session=SIGNAL):
    return series.prefix_len(session)


def _sliced(bars, session=SIGNAL):
    """The bars the classifier sees — strictly before ``session``."""
    return [b for b in bars if b.session < session]


# -- the fast path is the classifier ------------------------------------------


@pytest.mark.parametrize("drift", [0.01, 0.002, 0.0, -0.002, -0.01])
def test_the_trend_gate_agrees_with_the_classifier_on_every_drift(drift):
    bars = _bars(drift=drift)
    series = series_of("AAA", bars)
    assert series.passes_trend(_k(series)) is passes_trend_gate(_sliced(bars))


@pytest.mark.parametrize("adr_pct", [0.10, 0.05, 0.036, 0.035, 0.034, 0.02])
def test_the_adr_gate_agrees_with_the_classifier_across_the_floor(adr_pct):
    """Including exactly at the floor, which is inclusive on both sides."""
    bars = _bars(adr_pct=adr_pct)
    series = series_of("AAA", bars)
    assert series.passes_adr(_k(series)) is passes_adr_gate(_sliced(bars))


@pytest.mark.parametrize(
    "dollar_volume", [50_000_000.0, 10_000_001.0, 10_000_000.0, 9_999_999.0, 1_000.0]
)
def test_the_liquidity_gate_agrees_with_the_classifier_across_the_floor(dollar_volume):
    bars = _bars(dollar_volume=dollar_volume)
    series = series_of("AAA", bars)
    assert series.passes_liquidity(_k(series), US_FLOOR) is passes_liquidity_gate(
        _sliced(bars), "US", DEFAULT_CONTRACT
    )


def test_the_liquidity_gate_medians_a_short_window_exactly_as_the_app_does():
    """The app medians whatever the trailing 20 bars hold rather than requiring 20.

    Unreachable while the trend gate is in force — it needs 50 bars — and reachable
    the moment the ``no-trend`` variant drops it, which is why the shortfall
    behaviour is copied rather than tidied.
    """
    bars = _bars(sessions=SESSIONS[:6])
    series = series_of("AAA", bars)
    k = series.prefix_len(SESSIONS[5])
    assert k == 5
    expected = median_dollar_volume(_sliced(bars, SESSIONS[5])) >= US_FLOOR
    assert series.passes_liquidity(k, US_FLOOR) is expected


@pytest.mark.parametrize("bar_count", [0, 1, 19, 20, 49, 50])
def test_the_windows_open_where_the_classifier_opens_them(bar_count):
    """ADR needs 20 bars and the trend gate 50, and neither answers before that."""
    bars = _bars(sessions=SESSIONS[:bar_count]) if bar_count else []
    series = series_of("AAA", bars)
    if series is None:
        assert bar_count == 0
        return
    k = series.prefix_len(SESSIONS[bar_count])
    assert series.passes_adr(k) is passes_adr_gate(_sliced(bars, SESSIONS[bar_count]))
    assert series.passes_trend(k) is passes_trend_gate(
        _sliced(bars, SESSIONS[bar_count])
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"drift": -0.01},
        {"adr_pct": 0.02},
        {"dollar_volume": 1_000.0},
        {"drift": -0.01, "adr_pct": 0.02},
        {"adr_pct": 0.02, "dollar_volume": 1_000.0},
    ],
)
def test_full_gate_membership_agrees_with_the_classifier(kwargs):
    """The whole gate, not just its parts — this is the equality the run rests on."""
    bars = _bars(**kwargs)
    series = series_of("AAA", bars)
    expected = classifier_is_member(
        Candidate(symbol="AAA", name="", bars=bars), "US", SIGNAL, DEFAULT_CONTRACT
    )
    assert series.is_member(SIGNAL, ALL_GATES, US_FLOOR) is expected


def test_no_gate_reads_the_signal_session_s_own_bar():
    """A monstrous bar *on* the signal session cannot change that session's answer."""
    bars = _bars(adr_pct=0.02)
    loud = bars[:-1] + [
        Bar(SIGNAL, 50.0, 5_000.0, 1.0, 50.0, 50.0, 10_000_000_000),
    ]
    assert series_of("AAA", loud).is_member(
        SIGNAL, ALL_GATES, US_FLOOR
    ) is series_of("AAA", bars).is_member(SIGNAL, ALL_GATES, US_FLOOR)


def test_a_non_positive_low_fails_the_adr_gate_rather_than_raising():
    """One corrupt row must not take down a 5,495-symbol pass, and must not pass."""
    bars = _bars()
    bars[30] = Bar(bars[30].session, 50.0, 50.0, 0.0, 50.0, 50.0, 1_000_000)
    series = series_of("AAA", bars)
    assert series.passes_adr(series.prefix_len(bars[40].session)) is False


@pytest.mark.parametrize(
    "values",
    [[], [1.0], [1.0, 3.0], [3.0, 1.0, 2.0], [4.0, 1.0, 3.0, 2.0], [5.0] * 20],
)
def test_the_median_copy_is_the_app_s_median(values):
    """The app's ``_median`` is private, so this module copies it — and is pinned.

    Compared through :func:`screener.universe.median_dollar_volume`, which is the
    public function that median exists to serve, so the pin does not depend on a
    private name staying importable.
    """
    bars = [
        Bar(SESSIONS[i], 1.0, 1.0, 1.0, 1.0, 1.0, int(v)) for i, v in enumerate(values)
    ]
    assert _median([b.close * b.volume for b in bars]) == median_dollar_volume(bars)


# -- every variant reads one shared evaluation of the gates -------------------


def _four_names():
    return {
        "PASS": _series("PASS"),
        "DULL": _series("DULL", adr_pct=0.02),
        "FALLING": _series("FALLING", drift=-0.01),
        "THIN": _series("THIN", dollar_volume=1_000.0),
    }


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda v: v.name)
def test_the_batch_path_agrees_with_the_direct_one(variant):
    """One shared pass of the predicates must place every name where the direct
    per-variant evaluation does, or the variants are not sharing a baseline."""
    series = _four_names()
    flags = gate_flags_by_session(series, [SIGNAL], US_FLOOR)
    assert memberships_under(flags, variant.gates) == [
        members_at(series, SIGNAL, variant.gates, US_FLOOR)
    ]


def test_a_candidate_no_variant_can_admit_is_left_out_of_the_flags():
    """Carrying every rejected name at every session would cost more than it says."""
    series = {"NOPE": _series("NOPE", adr_pct=0.02, drift=-0.01, dollar_volume=1.0)}
    assert gate_flags_by_session(series, [SIGNAL], US_FLOOR) == [{}]
    for variant in VARIANTS:
        assert memberships_under(
            gate_flags_by_session(series, [SIGNAL], US_FLOOR), variant.gates
        ) == [[]]


# -- a variant drops a gate, and does nothing else ----------------------------


def test_the_variants_are_the_baseline_then_one_drop_per_gate():
    """Baseline first, then every gate dropped alone — that is the attribution.

    The two-gate cell is deliberately last and deliberately the only one: it exists
    because no single drop restores the sign, so it is a follow-up question rather
    than part of the one-variable-at-a-time table above it.
    """
    baseline, *rest = VARIANTS
    assert baseline.gates == ALL_GATES and baseline.dropped == frozenset()
    singles = [v for v in rest if len(v.dropped) == 1]
    assert {next(iter(v.dropped)) for v in singles} == ALL_GATES
    pairs = [v for v in rest if len(v.dropped) == 2]
    assert [v.name for v in pairs] == ["liquidity-only"]
    assert pairs[0].gates == frozenset({LIQUIDITY})
    assert len(singles) + len(pairs) == len(rest)


@pytest.mark.parametrize("gate", sorted(ALL_GATES))
def test_dropping_a_gate_only_ever_admits(gate):
    """A variant's membership is a superset of the baseline's, name for name."""
    series = _four_names()
    baseline = set(members_at(series, SIGNAL, ALL_GATES, US_FLOOR))
    widened = set(members_at(series, SIGNAL, ALL_GATES - {gate}, US_FLOOR))
    assert baseline <= widened


def test_each_dropped_gate_admits_the_name_that_gate_alone_rejects():
    """The isolation only means something if each drop moves its own name and no other."""
    series = _four_names()
    assert members_at(series, SIGNAL, ALL_GATES, US_FLOOR) == ["PASS"]
    assert members_at(series, SIGNAL, ALL_GATES - {ADR}, US_FLOOR) == ["DULL", "PASS"]
    assert members_at(series, SIGNAL, ALL_GATES - {TREND}, US_FLOOR) == [
        "FALLING",
        "PASS",
    ]
    assert members_at(series, SIGNAL, ALL_GATES - {LIQUIDITY}, US_FLOOR) == [
        "PASS",
        "THIN",
    ]


def test_the_instrument_type_test_is_not_a_variant():
    """No cell drops it, so an index cannot enter a field by having a gate removed."""
    series = {"^IXIC": _series("^IXIC")}
    for variant in VARIANTS:
        assert members_at(series, SIGNAL, variant.gates, US_FLOOR) == []


def test_membership_is_sorted_like_the_classifier_s():
    series = {s: _series(s) for s in ("ZZZ", "AAA", "MMM")}
    assert members_at(series, SIGNAL, ALL_GATES, US_FLOOR) == ["AAA", "MMM", "ZZZ"]


# -- the isolation refuses to report against a pool it cannot reproduce -------


def test_the_isolation_measures_every_variant_end_to_end():
    """A whole run over a tiny store, so the grid is actually reached and read.

    The reconstruction check passes here by construction — the store's universe rows
    were written from the same bars — which leaves this test doing the job the
    failure case cannot: exercising every step *after* the check, down to the cell
    the anchor is quoted at.
    """
    store = Store.memory()
    for symbol, kwargs in (
        ("AAA", {}),
        ("DULL", {"adr_pct": 0.02}),
        ("FALLING", {"drift": -0.01}),
        ("THIN", {"dollar_volume": 1_000.0}),
    ):
        store.append_bars("US", symbol, _bars(**kwargs))
    store.append_universe("US", SIGNAL, ["AAA"])

    isolation = run_isolation(store, "US", trades=[], sessions=[SIGNAL])

    assert isolation.check.exact
    assert {r.variant.name for r in isolation.results} == {v.name for v in VARIANTS}
    # Each drop admits its own name, so the field widens by exactly one per variant.
    assert isolation.by_name("all-three").members_per_session == 1.0
    for name in ("no-adr", "no-trend", "no-liquidity"):
        assert isolation.by_name(name).members_per_session == 2.0
    # Dropping two admits both their names: everything but the illiquid one.
    assert isolation.by_name("liquidity-only").members_per_session == 3.0
    # No trades, so there is nothing to place and no gap to read — and that must be
    # reported as absent rather than as a zero edge.
    assert isolation.by_name("all-three").placed == 0
    assert isolation.by_name("all-three").gap_pp is None


def test_the_dimension_rows_are_the_seven_dimension_replayed_score():
    """`Sector` is cross-sectional and is not reconstructed on the replay path.

    Reported as absent rather than as a zero hit rate, because a dimension nobody
    computed and a dimension nobody hit are different claims — and #194's acceptance
    criteria turn on the seven-dimension score never being mistaken for the app's
    nine-point one.
    """
    store = Store.memory()
    store.append_bars("US", "AAA", _bars())
    store.append_universe("US", SIGNAL, ["AAA"])
    isolation = run_isolation(store, "US", trades=[], sessions=[SIGNAL])
    # No trades here, so there is nothing to place and no contrast to draw.
    assert isolation.by_name("all-three").dimensions == ()


def test_a_dimension_gap_is_picks_minus_field_in_points():
    from backtest.field_gate_isolation import DimensionContrast

    row = DimensionContrast(dimension="ADR", weight=2, picks=0.77, field=0.613)
    assert row.gap_pp == pytest.approx(15.7)


def test_the_isolation_stops_when_the_rebuild_misses_the_store_s_own_rows():
    """A gate measured off a pool that is not the run's field measures the pool.

    The store here holds a universe row for a name it holds no bars for, so the
    rebuild cannot reproduce it. The run must stop rather than report cells.
    """
    store = Store.memory()
    bars = _bars()
    store.append_bars("US", "AAA", bars)
    store.append_universe("US", SIGNAL, ["AAA", "GHOST"])
    with pytest.raises(ReconstructionFailed) as excinfo:
        run_isolation(
            store,
            "US",
            trades=[],
            sessions=[SIGNAL],
            variants=[GateVariant("all-three", ALL_GATES, "")],
        )
    assert "does not reproduce" in str(excinfo.value)
