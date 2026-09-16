"""The star score: eight dimensions — seven boolean, one banded — nine weighted
points (spec §4.7, PRD #138, Tightness graded by #154, `Relative move` admitted
by ADR 0006 as rubric v4, #222).

`points ÷ 2` = stars, real range **0.0–4.5** (not 0–5): `Base length` is weighted
zero so the ninth point can never be earned, and since v4 nothing fires for every
detection by construction, so zero is reachable. Auditable rather than
continuous — the one graded dimension is banded to integral points — because the
score is the default sort of the only list in the app and a sort key you cannot
audit is one you will not trust. The score knows nothing about the stop and
nothing about the regime — every input below is a base signal, an index-relative
move or a sector share.

The weights encode the method's *revealed selection* (ADR 0001): the ×2 goes to
the two sharpest selectors in §5b's contrast (Tightness +20.8pp, ADR +29.4pp),
the ×0 to Base length's −13.4pp wrong-way gap, and Orderliness drops to ×1 on its
−9.1pp. Signs of the gaps license the *direction*; nothing here reads a value.
"""

from datetime import date

from screener.detection import DETECTOR_VERSION, Detection
from screener.score import DIMENSIONS, PROVISIONAL, RUBRIC_VERSION, star_score


def _det(
    *,
    cluster_k=5,
    range_3bar_adr=0.80,
    churn_l=0.45,
    base_len=10,
    sma20_rising=True,
    dryup=0.90,
    adr=0.06,
):
    """A detection whose scored signals are individually dialable so each
    dimension can be flipped in isolation. Fields not scored are filler."""
    return Detection(
        symbol="AAA", session=date(2026, 8, 5), detector_version=DETECTOR_VERSION,
        trigger=100.0, stop=3.0, stopw_adr=1.5, base_len=base_len, move_gain=103.0,
        adr=adr, close=98.0, cluster_k=cluster_k, cluster_high=100.0,
        cluster_low=97.0, cluster_range_adr=0.99, range_3bar_adr=range_3bar_adr,
        line_ok=True, touch_zones=2,
        overshoot_adr=0.0, slope=-0.001, line_end=99.9, base_low=97.0,
        churn_l=churn_l, sma20_rising=sma20_rising, dryup=dryup,
    )


# Every cross-sectional input hitting: the name outran the index by one ADR and
# its sector carries a fifth of the 1m board.
ALL_HIT = dict(relative_move=1.0, sector_share=0.20)


def test_every_dimension_hitting_is_the_four_and_a_half_star_ceiling():
    # The ceiling is 9 points, not 10: Base length is worth zero, so hitting it
    # buys nothing and the top of the scale is 4.5 stars.
    stars, breakdown = star_score(_det(), **ALL_HIT)
    assert stars == 4.5
    assert len(breakdown) == len(DIMENSIONS) == 8
    assert all(d.hit for d in breakdown)
    assert sum(d.weight for d in breakdown) == 9


def test_zero_stars_is_reachable_now_that_no_dimension_fires_by_construction():
    # v3's permanent half-star floor was `Prior move`, true of every detection
    # (the decile gate is a detection precondition). v4 retires it, so a
    # detection missing every dimension scores 0.0 — the floor is gone (#222).
    stars, _ = star_score(
        _det(range_3bar_adr=2.90, churn_l=0.10, base_len=20, sma20_rising=False,
             dryup=0.99, adr=0.04),
        relative_move=-0.5, sector_share=0.05,
    )
    assert stars == 0.0


def test_the_relative_move_is_scored_at_one_point_above_zero():
    # ADR 0006 admitted it at ×1 from the selection-gap ordering (Δ +3.6pp ranks
    # below Tightness and MA support). Hit strictly above the pre-registered cut
    # of zero: the name outran the index over six months.
    base = dict(sector_share=0.20)
    outran = star_score(_det(), relative_move=0.25, **base)[0]
    lagged = star_score(_det(), relative_move=-0.25, **base)[0]
    level = star_score(_det(), relative_move=0.0, **base)[0]
    assert outran - lagged == 0.5
    assert level == lagged  # the cut is strict; a tie is a miss


def test_an_absent_relative_move_scores_a_miss_and_carries_no_value():
    # `None` is absent — the name had not listed six months ago, or has no ADR.
    # Absent scores False, exactly as `relative_move_hit` reads it, and the row
    # carries no value rather than a zero sitting on the cut.
    stars, breakdown = star_score(_det(), relative_move=None, sector_share=0.20)
    row = next(d for d in breakdown if d.dimension == "Relative move")
    assert stars == 4.0
    assert row.hit is False
    assert row.value is None


def test_the_relative_move_row_carries_its_value_in_adr_units():
    # The stored value is the degree, in ADR units, so ADR 0004's grading
    # question can be asked of history without re-scoring it. Not graded today:
    # the row is worth its whole weight when it hits and nothing otherwise.
    _, breakdown = star_score(_det(), relative_move=2.75, sector_share=0.20)
    row = next(d for d in breakdown if d.dimension == "Relative move")
    assert row.value == 2.75
    assert row.weight == 1
    assert row.hit is True


def test_adr_is_double_weighted_and_moves_a_full_star():
    # ADR ×2 — the sharpest selector in §5b (+29.4pp).
    hit = star_score(_det(adr=0.06), **ALL_HIT)[0]
    miss = star_score(_det(adr=0.04), **ALL_HIT)[0]
    assert hit - miss == 1.0


def test_orderliness_is_single_weighted_and_moves_half_a_star():
    # Orderliness ×1 — he hits it less than the field (−9.1pp).
    hit = star_score(_det(churn_l=0.45), **ALL_HIT)[0]
    miss = star_score(_det(churn_l=0.10), **ALL_HIT)[0]
    assert hit - miss == 0.5


def test_tightness_stays_double_weighted_and_moves_a_full_star():
    # Still ×2 — but graded (#154), so the full star is the span between the
    # quietest band and the widest, not between two cluster_k values.
    with_tight = star_score(_det(range_3bar_adr=0.80), **ALL_HIT)[0]
    without_tight = star_score(_det(range_3bar_adr=2.80), **ALL_HIT)[0]
    assert with_tight - without_tight == 1.0


def test_cluster_k_no_longer_moves_the_score():
    # v2 scored `cluster_k >= 5`; v3 grades the three-bar range instead. The row
    # still records the old verdict (so v2 can re-score it), but the live rubric
    # does not read it.
    assert star_score(_det(cluster_k=7), **ALL_HIT)[0] == star_score(
        _det(cluster_k=3), **ALL_HIT
    )[0]


def test_base_length_is_weighted_zero_and_never_moves_the_score():
    # Zeroed on its −13.4pp wrong-way gap: it is measured, worth nothing, and
    # cannot change a star whether it hits or misses.
    hit = star_score(_det(base_len=10), **ALL_HIT)[0]
    miss = star_score(_det(base_len=20), **ALL_HIT)[0]
    assert hit == miss


def test_base_length_keeps_a_visible_zero_weight_row():
    # The dimension stays in the breakdown at weight 0 — deleting it would make the
    # rubric look as though it never considered base length at all (PRD #138).
    _, breakdown = star_score(_det(), **ALL_HIT)
    base_len_row = next(d for d in breakdown if d.dimension == "Base length")
    assert base_len_row.weight == 0


def test_the_thresholds_are_the_published_set():
    # Weights moved; the boolean thresholds did not. Each dimension awards on its
    # published boundary and denies just under it.
    def stars_with(**kw):
        return star_score(_det(**{k: v for k, v in kw.items() if k in
                                  ("cluster_k", "range_3bar_adr", "churn_l",
                                   "base_len", "sma20_rising", "dryup", "adr")}),
                          relative_move=kw.get("relative_move", 1.0),
                          sector_share=kw.get("sector_share", 0.20))[0]

    all_hit = stars_with()
    assert all_hit == 4.5
    # base tightness graded on the 3-bar range (×2) ; dryup <= 0.95 (×1) ;
    # adr >= 0.05 (×2)
    assert stars_with(range_3bar_adr=1.50) == 4.0
    assert stars_with(dryup=0.96) == 4.0
    assert stars_with(adr=0.05) == 4.5          # inclusive at the boundary
    assert stars_with(adr=0.049) == 3.5         # ×2, so a full star
    # base_len <= 14 threshold still evaluated, but ×0 so no star moves either side
    assert stars_with(base_len=14) == 4.5
    assert stars_with(base_len=15) == 4.5
    # orderliness band 0.30 .. 0.60 inclusive (×1); sector share >= 0.10 (×1)
    assert stars_with(churn_l=0.30) == 4.5
    assert stars_with(churn_l=0.60) == 4.5
    assert stars_with(churn_l=0.61) == 4.0
    assert stars_with(sector_share=0.10) == 4.5
    assert stars_with(sector_share=0.09) == 4.0
    # relative move strictly above zero (×1)
    assert stars_with(relative_move=0.01) == 4.5
    assert stars_with(relative_move=0.0) == 4.0


def test_the_breakdown_names_all_eight_dimensions_with_their_weights():
    _, breakdown = star_score(_det(), **ALL_HIT)
    names = [d.dimension for d in breakdown]
    # `Relative move` takes the slot `Prior move` held (#222); nothing else moves.
    assert names == [
        "Tightness", "Orderliness", "Relative move", "Base length",
        "MA support", "Volume", "Sector", "ADR",
    ]
    weights = {d.dimension: d.weight for d in breakdown}
    assert weights["Tightness"] == 2
    assert weights["ADR"] == 2
    assert weights["Orderliness"] == 1
    assert weights["Base length"] == 0
    assert weights["Relative move"] == weights["MA support"] == 1
    assert weights["Volume"] == weights["Sector"] == 1


def test_the_rubric_version_is_four_and_relative_move_is_declared_provisional():
    # The stamp that lets a frozen digest star and a derived-on-read app star be
    # compared like with like (PRD #138). v4 is the admission of `Relative move`
    # (ADR 0006), which is provisional and owed a re-read by the candidate
    # outcome test — declared beside the table so the backtest can tell an
    # admitted-provisionally row from a candidate that leaked into the rubric.
    assert RUBRIC_VERSION == 4
    assert set(PROVISIONAL) == {"Relative move"}
    assert "Relative move" in {name for name, _w in DIMENSIONS}


def test_the_rubric_table_carries_the_superseded_versions_alongside_the_live_one():
    # The paired A2 re-run (#136) re-scores the *same* field under several rubrics
    # so a rubric change is separated from a field change. That needs every
    # superseded version kept beside the live one, keyed by version stamp.
    from screener.score import RUBRICS

    assert set(RUBRICS) == {1, 2, 3, RUBRIC_VERSION}
    v1, v4 = RUBRICS[1].weights, RUBRICS[RUBRIC_VERSION].weights
    # v1 is the ten-point rubric: Tightness/Orderliness ×2, everything else ×1.
    assert v1 == {
        "Tightness": 2, "Orderliness": 2, "Prior move": 1, "Base length": 1,
        "MA support": 1, "Volume": 1, "Sector": 1, "ADR": 1,
    }
    assert sum(v1.values()) == 10
    # v4 mirrors the live DIMENSIONS table, and totals nine.
    assert v4 == {name: weight for name, weight in DIMENSIONS}
    assert sum(v4.values()) == 9


def test_the_rubric_table_retains_v2_and_v3_unedited():
    from screener.score import RUBRICS

    # v2 is the nine-point boolean table PRD #138 shipped. Spelled out rather
    # than compared against DIMENSIONS: a superseded version records what
    # shipped, so this assertion has to fail if a future weight edit drags it
    # along with the live table.
    v2 = {
        "Tightness": 2, "Orderliness": 1, "Prior move": 1, "Base length": 0,
        "MA support": 1, "Volume": 1, "Sector": 1, "ADR": 2,
    }
    assert RUBRICS[2].weights == v2
    assert RUBRICS[2].bands == {}
    # v3 is v2's weights with Tightness graded (#154) — the rubric that shipped
    # until #222, and the one every digest before it froze its stars under.
    assert RUBRICS[3].weights == v2
    assert set(RUBRICS[3].bands) == {"Tightness"}
    # Only the graded dimension is banded, under v3 and v4 alike.
    assert set(RUBRICS[RUBRIC_VERSION].bands) == {"Tightness"}


def test_stars_under_rescore_a_breakdown_under_an_arbitrary_rubric():
    # stars_under re-totals a breakdown under a supplied rubric, so one field's
    # detections can be scored under any version without re-detecting. Under the
    # live rubric it reproduces star_score exactly.
    from screener.score import RUBRICS, stars_under

    det = _det(adr=0.06, churn_l=0.45, base_len=10)  # ADR + Orderliness + Base all hit
    stars, breakdown = star_score(det, **ALL_HIT)
    assert stars_under(breakdown, RUBRICS[RUBRIC_VERSION]) == stars
    # Under v1 the same booleans score differently: ADR was ×1 not ×2, Orderliness
    # ×2 not ×1 (net 0), Base length ×1 not ×0 (+1 point), Prior move's constant
    # point replaces Relative move's earned one (net 0) → +0.5 star.
    assert stars_under(breakdown, RUBRICS[1]) == stars + 0.5


def test_a_v3_rescore_of_a_v4_row_is_exact_in_both_directions():
    # The #136 pairing holds the field fixed and swaps only the rubric. `Prior
    # move` was true of every detection by construction (the decile gate is a
    # detection precondition), so v1–v3 always awarded its point; a v4 row no
    # longer writes it. Re-scored under v3 the row must still earn what shipped,
    # or the paired re-run's "before" would move by half a star along with the
    # "after": a v4 row missing Relative move re-scores under v3 with the
    # constant's point back, and one hitting it scores the same under both,
    # since the two ×1s swap places. v1 and v2 credit it the same way.
    from screener.score import RUBRICS, stars_under

    _, lagged = star_score(_det(), relative_move=-1.0, sector_share=0.20)
    assert stars_under(lagged, RUBRICS[RUBRIC_VERSION]) == 4.0
    assert stars_under(lagged, RUBRICS[3]) == 4.5
    assert stars_under(lagged, RUBRICS[2]) == 4.5
    _, outran = star_score(_det(), relative_move=1.0, sector_share=0.20)
    assert stars_under(outran, RUBRICS[RUBRIC_VERSION]) == 4.5
    assert stars_under(outran, RUBRICS[3]) == 4.5


def test_a_v3_row_still_rescores_under_v3_without_double_crediting_the_constant():
    # A breakdown written under v3 carries the Prior move row itself. Its constant
    # is credited only when the row is absent, so an old row is not paid twice.
    from screener.score import RUBRICS, Dimension, stars_under

    v3_row = [
        Dimension("Tightness", 2, True, 0.5), Dimension("Orderliness", 1, True),
        Dimension("Prior move", 1, True), Dimension("Base length", 0, True),
        Dimension("MA support", 1, True), Dimension("Volume", 1, True),
        Dimension("Sector", 1, True), Dimension("ADR", 2, True),
    ]
    assert stars_under(v3_row, RUBRICS[3]) == 4.5
    # And under v4 the same old row has no Relative move to earn: 4.0, absent
    # read as a miss — exactly how the live rubric reads an absent value.
    assert stars_under(v3_row, RUBRICS[RUBRIC_VERSION]) == 4.0


# -- v3: Tightness graded, and the value persisted so v2 still re-scores ------


def test_tightness_is_graded_from_the_three_bar_range_not_the_cluster_k():
    # #145/#154: the ×2 dimension stops being `cluster_k >= 5` and grades the
    # real-valued base tightness the row carries. §3b's own bucket edges: two
    # points under 1.0 ADR, one through 2.0, nothing beyond.
    quiet = star_score(_det(range_3bar_adr=0.80), **ALL_HIT)[0]
    middling = star_score(_det(range_3bar_adr=1.60), **ALL_HIT)[0]
    wide = star_score(_det(range_3bar_adr=2.50), **ALL_HIT)[0]
    assert quiet - middling == 0.5
    assert middling - wide == 0.5


def test_the_tightness_bands_are_inclusive_at_their_published_edges():
    assert star_score(_det(range_3bar_adr=1.00), **ALL_HIT)[0] == 4.5
    assert star_score(_det(range_3bar_adr=1.01), **ALL_HIT)[0] == 4.0
    assert star_score(_det(range_3bar_adr=2.00), **ALL_HIT)[0] == 4.0
    assert star_score(_det(range_3bar_adr=2.01), **ALL_HIT)[0] == 3.5


def test_the_graded_dimension_keeps_the_nine_point_ceiling_and_integral_points():
    # Bands, not a fraction: the ceiling stays nine points and every star lands on
    # a half — so the "n/9 ÷ 2" arithmetic and every star display are untouched.
    stars, breakdown = star_score(_det(range_3bar_adr=0.50), **ALL_HIT)
    assert stars == 4.5
    assert sum(d.weight for d in breakdown) == 9
    assert (stars * 2) % 1 == 0


def test_the_breakdown_persists_the_value_not_just_the_verdict():
    # The row carries the graded quantity itself, so each rubric version owns its
    # own value → points mapping (#154). Two rows carry a value: Tightness, which
    # is graded, and Relative move, kept in ADR units for a grading question not
    # yet asked (ADR 0004). Every other row is a bare boolean.
    _, breakdown = star_score(
        _det(range_3bar_adr=1.31), relative_move=0.4, sector_share=0.20
    )
    rows = {d.dimension: d for d in breakdown}
    assert rows["Tightness"].value == 1.31
    assert rows["Relative move"].value == 0.4
    assert all(
        d.value is None for d in breakdown
        if d.dimension not in ("Tightness", "Relative move")
    )


def test_a_v3_row_still_carries_the_v2_tightness_verdict():
    # v2's rule was `cluster_k >= 5`, which no value can reconstruct — so the row
    # keeps the boolean alongside the value. Both are properties of the setup.
    _, long_k = star_score(_det(cluster_k=5, range_3bar_adr=2.50), **ALL_HIT)
    _, short_k = star_score(_det(cluster_k=4, range_3bar_adr=0.50), **ALL_HIT)
    assert next(d for d in long_k if d.dimension == "Tightness").hit is True
    assert next(d for d in short_k if d.dimension == "Tightness").hit is False


def test_a_v2_rescore_of_a_graded_row_reproduces_the_paired_run_exactly():
    # The #136 pairing scores one field under both rubrics without re-detecting.
    # A graded row must not break that: re-scored under v2 the Tightness
    # dimension goes back to being the boolean, whatever v3/v4 graded it.
    from screener.score import RUBRICS, stars_under

    # k = 4 (v2 withholds Tightness) but a 0.5 ADR three-bar range (the graded
    # rubrics award both points): the two disagree by a full star, in the right
    # direction.
    stars_v4, breakdown = star_score(_det(cluster_k=4, range_3bar_adr=0.50), **ALL_HIT)
    assert stars_under(breakdown, RUBRICS[RUBRIC_VERSION]) == stars_v4 == 4.5
    assert stars_under(breakdown, RUBRICS[3]) == 4.5
    assert stars_under(breakdown, RUBRICS[2]) == 3.5
    # v1's ten-point table re-totals the same booleans as it always did.
    assert stars_under(breakdown, RUBRICS[1]) == 4.0


def test_a_graded_rubric_falls_back_to_the_boolean_when_a_row_carries_no_value():
    # A breakdown written before the value existed (or struck by the replay) still
    # re-totals under the graded rubrics rather than silently scoring zero.
    from screener.score import RUBRICS, Dimension, stars_under

    valueless = [Dimension("Tightness", 2, True), Dimension("ADR", 2, True)]
    assert stars_under(valueless, RUBRICS[RUBRIC_VERSION]) == 2.0
    # Under v3 the absent constant is credited on top: 2.5.
    assert stars_under(valueless, RUBRICS[3]) == 2.5
