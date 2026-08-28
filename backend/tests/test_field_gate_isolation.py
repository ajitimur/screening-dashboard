"""#211's gate isolation: the fast path must be the classifier, and a dropped gate
must only ever admit.

:mod:`backtest.field_gate_isolation` exists to answer one question — *which* of the
stateless universe's three gates reverses the rubric's edge — and it can only answer
it if its rebuilt membership is the run's own membership. Two things therefore have
to hold, and both are pinned here rather than assumed:

- **Its gates are :mod:`backtest.universe`'s gates.** The module holds each
  candidate's bars as parallel lists and indexes them per session instead of
  re-slicing the symbol's history. These tests put the two orders side by side on the
  same bars and require the same answer, so the indexed path cannot drift from the
  classifier it stands in for.
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

import inspect
from datetime import date, timedelta
from typing import Callable

import pytest

from screener import universe as app_universe
from screener.bars import Bar
from screener.store import Store
from screener.universe import median_dollar_volume

from backtest import universe as backtest_universe
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
    ALL_GATES,
    HYSTERESIS_EXIT,
    LIQUIDITY,
    TREND,
    VARIANTS,
    VOLATILITY,
    WINDOW_BURN_IN,
    WINDOW_END,
    WINDOW_START,
    GateFlags,
    ReconstructionFailed,
    UniverseGateSet,
    band_effects,
    band_threshold,
    format_isolation,
    format_payload,
    gate_flags_by_session,
    hysteretic_memberships,
    isolation_payload,
    members_at,
    memberships_for,
    memberships_under,
    merge_payloads,
    run_isolation,
    series_of,
    window_sessions,
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
    dollar_volume: float | Callable[[int], float] = 50_000_000.0,
    sessions: list[date] | None = None,
) -> list[Bar]:
    """Bars that clear every gate by default, one knob per gate.

    ``dollar_volume`` takes a function of the bar's index as well as a level, for
    the one case a level cannot express: a name whose turnover *changes*, which is
    what the hysteresis band exists to respond to.
    """
    out = []
    for i, s in enumerate(sessions or SESSIONS):
        p = price * (1 + drift) ** i
        dv = dollar_volume(i) if callable(dollar_volume) else dollar_volume
        out.append(
            Bar(
                session=s,
                open=p,
                high=p * (1 + adr_pct),
                low=p,
                close=p,
                adj_close=p,
                volume=max(1, round(dv / p)),
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
    behaviour is reused rather than tidied.
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


# -- every variant reads one shared evaluation of the gates -------------------


def _four_names():
    return {
        "PASS": _series("PASS"),
        "DULL": _series("DULL", adr_pct=0.02),
        "FALLING": _series("FALLING", drift=-0.01),
        "THIN": _series("THIN", dollar_volume=1_000.0),
    }


def test_a_candidate_no_variant_can_admit_is_left_out_of_the_flags():
    """Carrying every rejected name at every session would cost more than it says.

    A name below 0.8× the floor is out under the band too, so the pruning stays
    safe once a hysteretic variant reads the same flags.
    """
    series = {"NOPE": _series("NOPE", adr_pct=0.02, drift=-0.01, dollar_volume=1.0)}
    assert gate_flags_by_session(series, [SIGNAL], US_FLOOR) == [{}]
    for variant in VARIANTS:
        assert memberships_for(
            gate_flags_by_session(series, [SIGNAL], US_FLOOR),
            variant,
            prior={"NOPE"},
        ) == [[]]


# -- a variant drops a gate, and does nothing else ----------------------------


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
    assert members_at(series, SIGNAL, ALL_GATES - {VOLATILITY}, US_FLOOR) == ["DULL", "PASS"]
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
    # On one session from a cold start the band has no prior to hold anything by,
    # so each hysteretic row lands on its stateless twin. What the band is worth
    # needs a walk, and the walk is measured in its own tests below.
    assert isolation.by_name("all-three+band").members_per_session == 1.0
    assert isolation.by_name("liquidity-only+band").members_per_session == 3.0
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
            variants=[UniverseGateSet("all-three", ALL_GATES, "")],
        )
    assert "does not reproduce" in str(excinfo.value)


# -- the band: what the app's hysteresis is worth, measured beside the contract


APP_FLOOR = app_universe.LIQUIDITY_FLOOR["US"]


# The four flag positions, as the walk reads them: the three gates, then the
# fourth answer the band needs — "does this name still clear 0.8× the floor?".
def _flags(trend=True, volatility=True, liquidity=True, held=True):
    return GateFlags(trend, volatility, liquidity, held)


# A name at 1.0× or better enters; one between 0.8× and 1.0× is held but cannot
# enter; one below 0.8× is out under every rule.
ENTERS = _flags(liquidity=True, held=True)
IN_BAND = _flags(liquidity=False, held=True)
BELOW_BAND = _flags(liquidity=False, held=False)


def test_the_band_is_the_apps_own_constant_and_never_a_copy_of_it():
    """0.8 is the app's number (spec §4.1, ticket 05 D11), imported not restated.

    And it stays out of :mod:`backtest.universe`, whose statelessness is a
    recorded contract property with its own test — this is a measurement variant
    that lives beside that classifier, never an edit to it.
    """
    assert HYSTERESIS_EXIT is app_universe.HYSTERESIS_EXIT
    assert not hasattr(backtest_universe, "HYSTERESIS_EXIT")


def test_the_contracts_classifier_is_still_stateless():
    """#213 measures the band; it does not give the contract one."""
    assert "prior_members" not in inspect.signature(
        backtest_universe.classify
    ).parameters
    bars = _bars()
    once = backtest_universe.classify(
        "US",
        [Candidate(symbol="AAA", name="", bars=bars)],
        SIGNAL,
        DEFAULT_CONTRACT,
    )
    assert once == backtest_universe.classify(
        "US", [Candidate(symbol="AAA", name="", bars=bars)], SIGNAL, DEFAULT_CONTRACT
    )


def test_the_threshold_is_asymmetric_the_way_the_app_is():
    """More evidence to leave than to enter: 1.0× in, 0.8× out."""
    assert band_threshold(APP_FLOOR, held=False) == APP_FLOOR
    assert band_threshold(APP_FLOOR, held=True) == APP_FLOOR * 0.8


@pytest.mark.parametrize("held", [True, False])
@pytest.mark.parametrize("multiple", [1.5, 1.01, 1.0, 0.99, 0.9, 0.81, 0.8, 0.79, 0.5])
def test_the_band_agrees_with_the_app_on_the_same_bars(multiple, held):
    """The variant's band predicate is :mod:`screener.universe`'s own behaviour.

    Asked at the app's own floor, over the bars the app would see — everything
    through t−1 — so the two sides differ in nothing but which code answers. The
    app's classifier is run whole rather than its private gate called, because
    what is being pinned is the band as the app applies it.
    """
    bars = _bars(dollar_volume=APP_FLOOR * multiple)
    knowable = _sliced(bars)
    series = series_of("AAA", bars)
    app_members = app_universe.classify(
        "US",
        [app_universe.Candidate(symbol="AAA", name="", resolved=True, bars=knowable)],
        [b.session for b in knowable],
        {"AAA"} if held else set(),
    )
    assert series.passes_liquidity_band(_k(series), APP_FLOOR, held=held) is (
        app_members == ["AAA"]
    )


def test_the_entry_side_of_the_band_is_the_plain_liquidity_gate():
    """A non-member enters at 1.0×, which is the gate the other variants apply."""
    for multiple in (1.5, 1.0, 0.99, 0.5):
        series = _series(dollar_volume=US_FLOOR * multiple)
        k = _k(series)
        assert series.passes_liquidity_band(k, US_FLOOR, held=False) is (
            series.passes_liquidity(k, US_FLOOR)
        )


# -- the walk -----------------------------------------------------------------


def test_a_member_is_held_in_the_band_and_a_non_member_is_not_admitted_by_it():
    """The whole asymmetry, on one name: it cannot enter on a band reading, it is
    held on one, and once it drops below the band it needs 1.0× to come back."""
    walk = [
        {"A": IN_BAND},
        {"A": ENTERS},
        {"A": IN_BAND},
        {"A": BELOW_BAND},
        {"A": IN_BAND},
    ]
    assert hysteretic_memberships(walk, ALL_GATES) == [[], ["A"], ["A"], [], []]
    # Without the band the same name is a member only where it clears 1.0×.
    assert memberships_under(walk, ALL_GATES) == [[], ["A"], [], [], []]


def test_the_band_relaxes_the_liquidity_floor_and_nothing_else():
    """A held name still has to clear the gates the variant applies — the app's
    band is on the liquidity floor alone (``screener.universe._is_member``)."""
    walk = [
        {"A": ENTERS},
        {"A": _flags(volatility=False, liquidity=False)},
        {"A": _flags(trend=False, liquidity=False)},
    ]
    assert hysteretic_memberships(walk, ALL_GATES) == [["A"], [], []]
    assert hysteretic_memberships(walk, frozenset({LIQUIDITY})) == [["A"], ["A"], ["A"]]


def test_a_walk_starts_from_the_prior_it_is_given():
    """Which is what a warm-up is: state carried in, not assumed empty."""
    walk = [{"A": IN_BAND}]
    assert hysteretic_memberships(walk, ALL_GATES) == [[]]
    assert hysteretic_memberships(walk, ALL_GATES, prior={"A"}) == [["A"]]


def test_the_band_only_ever_admits():
    """Session for session, a hysteretic membership is a superset of the same
    gates without the band — so a cell that moves cannot have moved by exclusion."""
    walk = [
        {"A": ENTERS, "B": IN_BAND},
        {"A": IN_BAND, "B": ENTERS},
        {"A": BELOW_BAND, "B": IN_BAND},
    ]
    for gates in (ALL_GATES, frozenset({LIQUIDITY})):
        for plain, banded in zip(
            memberships_under(walk, gates), hysteretic_memberships(walk, gates)
        ):
            assert set(plain) <= set(banded)


def test_the_band_is_a_no_op_where_the_liquidity_gate_is_dropped():
    """Nothing else in the universe is hysteretic, so a variant without the
    liquidity floor has no band to apply."""
    walk = [{"A": ENTERS}, {"A": BELOW_BAND}]
    gates = ALL_GATES - {LIQUIDITY}
    assert hysteretic_memberships(walk, gates) == memberships_under(walk, gates)


def test_the_walk_is_sorted_like_the_classifier_s():
    """So a band membership is comparable to the store's rows and to the stateless
    variants' without either side being re-ordered first."""
    walk = [{"ZZZ": ENTERS, "AAA": ENTERS, "MMM": ENTERS}]
    assert hysteretic_memberships(walk, ALL_GATES) == [["AAA", "MMM", "ZZZ"]]


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda v: v.name)
def test_the_batch_path_agrees_with_the_direct_one_under_every_variant(variant):
    """Including the hysteretic ones, whose direct path takes the prior in hand."""
    series = _four_names()
    prior = {"THIN"}
    flags = gate_flags_by_session(series, [SIGNAL], US_FLOOR)
    assert memberships_for(flags, variant, prior=prior) == [
        members_at(
            series,
            SIGNAL,
            variant.gates,
            US_FLOOR,
            prior=prior if variant.hysteresis else (),
        )
    ]


def test_memberships_for_drops_the_warm_up_sessions_it_walked_through():
    """The warm-up exists to settle the band, not to be reported."""
    walk = [{"A": ENTERS}, {"A": IN_BAND}, {"A": IN_BAND}]
    banded = next(v for v in VARIANTS if v.hysteresis and LIQUIDITY in v.gates)
    plain = next(v for v in VARIANTS if not v.hysteresis and v.gates == banded.gates)
    assert memberships_for(walk, banded, warm_up=1) == [["A"], ["A"]]
    assert memberships_for(walk, plain, warm_up=1) == [[], []]


# -- the variants the band makes possible -------------------------------------


def test_the_stateless_variants_are_the_baseline_then_one_drop_per_gate():
    """Baseline first, then every gate dropped alone — that is the attribution.

    The two-gate cell is deliberately last of the stateless rows and deliberately
    the only one: it exists because no single drop restores the sign, so it is a
    follow-up question rather than part of the one-variable-at-a-time table.
    """
    stateless = [v for v in VARIANTS if not v.hysteresis]
    baseline, *rest = stateless
    assert baseline.gates == ALL_GATES and baseline.dropped == frozenset()
    singles = [v for v in rest if len(v.dropped) == 1]
    assert {next(iter(v.dropped)) for v in singles} == ALL_GATES
    pairs = [v for v in rest if len(v.dropped) == 2]
    assert [v.name for v in pairs] == ["liquidity-only"]
    assert pairs[0].gates == frozenset({LIQUIDITY})
    assert len(singles) + len(pairs) == len(rest)


def test_every_hysteretic_variant_has_a_stateless_twin_to_be_read_against():
    """A band cell means nothing on its own — what it is worth is the difference
    from the same gates without it, so each one must have that row to subtract."""
    banded = [v for v in VARIANTS if v.hysteresis]
    assert {v.name for v in banded} == {"all-three+band", "liquidity-only+band"}
    for v in banded:
        assert LIQUIDITY in v.gates, "a band on a dropped floor measures nothing"
        twin = [w for w in VARIANTS if not w.hysteresis and w.gates == v.gates]
        assert len(twin) == 1


def test_a_band_effect_is_the_twin_row_subtracted():
    """What the band is worth is a difference, and the page quotes it in points —
    so the arithmetic behind "+0.40pp of `in_field`, +0.05pp of gap" is pinned here
    rather than done by hand on the way into the write-up."""
    effects = band_effects(
        [
            {
                "name": "liquidity-only",
                "gates": ["liquidity"],
                "hysteresis": False,
                "members_per_session": 1687.8,
                "in_field": 322,
                "placed": 503,
                "gap_pp": 0.72,
            },
            {
                "name": "liquidity-only+band",
                "gates": ["liquidity"],
                "hysteresis": True,
                "members_per_session": 1700.0,
                "in_field": 324,
                "placed": 503,
                "gap_pp": 0.60,
            },
        ]
    )
    assert len(effects) == 1
    effect = effects[0]
    assert effect["variant"] == "liquidity-only+band"
    assert effect["baseline"] == "liquidity-only"
    assert effect["gap_delta_pp"] == pytest.approx(-0.12)
    assert effect["in_field_delta"] == 2
    assert effect["in_field_delta_pp"] == pytest.approx(0.3976, abs=1e-3)
    assert effect["members_delta"] == pytest.approx(12.2)


def test_a_band_effect_is_absent_rather_than_zero_when_a_row_is_unmeasured():
    """A cell nobody measured and a band worth nothing are different claims."""
    effects = band_effects(
        [
            {
                "name": "all-three+band",
                "gates": ["liquidity", "trend", "volatility"],
                "hysteresis": True,
                "members_per_session": 1.0,
                "in_field": 0,
                "placed": 0,
                "gap_pp": None,
            },
        ]
    )
    assert effects == []


# -- the whole isolation, with a band that had somewhere to come from ---------


def _fading(i):
    """1.5× the floor while a name is liquid, 0.9× — inside the band — after."""
    return US_FLOOR * (1.5 if i <= 42 else 0.9)


def _band_store():
    """A store where one name enters on the warm-up and then fades into the band.

    ``FADER``'s trailing median clears 1.0× on ``SESSIONS[52]`` (11 of its 20
    window bars are still the high level) and sits at 0.9× on both measured
    sessions. So the band's answer is not the plain gate's, and whether it is a
    member on the measured sessions depends on a session nobody reports.
    """
    store = Store.memory()
    store.append_bars("US", "AAA", _bars())
    store.append_bars("US", "FADER", _bars(dollar_volume=_fading))
    for session in (SESSIONS[55], SESSIONS[56]):
        store.append_universe("US", session, ["AAA"])
    return store


def test_the_band_variants_hold_a_name_the_stateless_gates_drop():
    """The whole isolation with a band that had somewhere to come from: the walk
    reaches the store, the warm-up carries state into the measured sessions, and the
    two band cells differ from their twins by the name the band holds."""
    isolation = run_isolation(
        _band_store(),
        "US",
        trades=[],
        sessions=[SESSIONS[55], SESSIONS[56]],
        warm_up=[SESSIONS[52], SESSIONS[53], SESSIONS[54]],
    )
    assert isolation.check.exact
    assert {r.variant.name for r in isolation.results} == {v.name for v in VARIANTS}
    assert isolation.by_name("all-three").members_per_session == 1.0
    assert isolation.by_name("all-three+band").members_per_session == 2.0
    assert isolation.by_name("liquidity-only").members_per_session == 1.0
    assert isolation.by_name("liquidity-only+band").members_per_session == 2.0


def test_without_a_warm_up_the_band_has_no_prior_to_hold_a_name_by():
    """Which is why the run warms it: a walk started cold cannot hold anything on
    its first session, and a name already inside the band never enters at all."""
    isolation = run_isolation(
        _band_store(), "US", trades=[], sessions=[SESSIONS[55], SESSIONS[56]]
    )
    assert isolation.by_name("all-three+band").members_per_session == 1.0
    assert isolation.by_name("all-three").members_per_session == 1.0


def test_the_warm_up_is_the_windows_own_burn_in():
    """The band settles over the sessions the anchor's window already discards,
    so no bar outside the reference study's window is read to settle it."""
    outside = [WINDOW_START - timedelta(days=1), WINDOW_END + timedelta(days=1)]
    inside = [WINDOW_START + timedelta(days=i) for i in range(WINDOW_BURN_IN + 5)]
    warm, measured = window_sessions(sorted(inside + outside))
    assert list(warm) + list(measured) == inside
    assert len(warm) == WINDOW_BURN_IN
    assert measured[0] == inside[WINDOW_BURN_IN]


# -- the report is the payload, and a subset can be merged into it -------------


def test_the_report_is_rendered_from_the_payload_it_records():
    """One formatter, reading the recorded figures — so a table can be re-rendered
    from ``backtest_gate_isolation.json`` without re-measuring anything."""
    store = Store.memory()
    store.append_bars("US", "AAA", _bars())
    store.append_universe("US", SIGNAL, ["AAA"])
    isolation = run_isolation(store, "US", trades=[], sessions=[SIGNAL])
    assert format_isolation(isolation) == format_payload(isolation_payload(isolation))


def _payload(variants, **overrides):
    payload = {
        "window": {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "burn_in": WINDOW_BURN_IN,
            "market": "US",
        },
        "detector_version": 3,
        "field": "whole",
        "rubric_version": 2,
        "stars": 3.5,
        "reconstruction": {"sessions": 821, "stored": 1, "rebuilt": 1,
                           "extra": 0, "missing": 0, "exact": True},
        "variants": variants,
    }
    payload.update(overrides)
    return payload


def _cell(name, gates, hysteresis=False, gap=1.0):
    return {
        "name": name,
        "gates": sorted(gates),
        "dropped": sorted(ALL_GATES - set(gates)),
        "note": "",
        "hysteresis": hysteresis,
        "members_per_session": 100.0,
        "field_detections": 10,
        "in_field": 300,
        "placed": 503,
        "in_field_share": 300 / 503,
        "picks_share": 0.14,
        "field_share": 0.13,
        "gap_pp": gap,
        "dimensions": [],
    }


def test_merging_keeps_the_recorded_cells_and_adds_the_measured_ones():
    """The five stateless rows were run three times across two implementations;
    #213 adds two rows to them rather than re-measuring what they already say."""
    recorded = _payload([_cell(v.name, v.gates, v.hysteresis)
                         for v in VARIANTS if not v.hysteresis])
    fresh = _payload([_cell(v.name, v.gates, v.hysteresis, gap=-2.0)
                      for v in VARIANTS if v.hysteresis])
    merged = merge_payloads(recorded, fresh)
    assert [c["name"] for c in merged["variants"]] == [v.name for v in VARIANTS]
    assert merged["variants"][0]["gap_pp"] == 1.0
    assert [c["gap_pp"] for c in merged["variants"] if c["hysteresis"]] == [-2.0, -2.0]
    assert len(merged["band_effects"]) == 2


def test_merging_replaces_a_cell_that_was_measured_again():
    """A re-measured cell wins. Merging is for adding rows to a table, never for
    keeping a stale figure alive beside the run that superseded it."""
    recorded = _payload([_cell("all-three", ALL_GATES, gap=1.0)])
    fresh = _payload([_cell("all-three", ALL_GATES, gap=9.0)])
    merged = merge_payloads(recorded, fresh)
    assert [c["gap_pp"] for c in merged["variants"]] == [9.0]


def test_merging_refuses_cells_measured_over_a_different_window():
    """Rows from two windows in one table would read as one measurement."""
    recorded = _payload([_cell("all-three", ALL_GATES)])
    fresh = _payload(
        [_cell("all-three+band", ALL_GATES, hysteresis=True)],
        window={"start": "2015-01-01", "end": "2018-12-31", "burn_in": 126,
                "market": "US"},
    )
    with pytest.raises(ValueError) as excinfo:
        merge_payloads(recorded, fresh)
    assert "window" in str(excinfo.value)
