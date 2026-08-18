"""The star score: eight boolean dimensions, nine weighted points (spec §4.7,
PRD #138).

`points ÷ 2` = stars, real range **0.5–4.5** (not 0–5): `Prior move` fires for
every detection by construction so half a star is a permanent floor, and
`Base length` is weighted zero so the ninth point can never be earned. Booleans,
not continuous, because the score is the default sort of the only list in the app
and a sort key you cannot audit is one you will not trust. The score knows nothing
about the stop and nothing about the regime — every input below is a base signal,
a rank percentile or a sector share.

The weights encode the method's *revealed selection* (ADR 0001): the ×2 goes to
the two sharpest selectors in §5b's contrast (Tightness +20.8pp, ADR +29.4pp),
the ×0 to Base length's −13.4pp wrong-way gap, and Orderliness drops to ×1 on its
−9.1pp. Signs of the gaps license the *direction*; nothing here reads a value.
"""

from datetime import date

from screener.detection import DETECTOR_VERSION, Detection
from screener.score import DIMENSIONS, RUBRIC_VERSION, star_score


def _det(
    *,
    cluster_k=5,
    churn_l=0.45,
    base_len=10,
    sma20_rising=True,
    dryup=0.90,
    adr=0.06,
):
    """A detection whose eight scored signals are individually dialable so each
    dimension can be flipped in isolation. Fields not scored are filler."""
    return Detection(
        symbol="AAA", session=date(2026, 8, 5), detector_version=DETECTOR_VERSION,
        trigger=100.0, stop=3.0, stopw_adr=1.5, base_len=base_len, move_gain=103.0,
        adr=adr, close=98.0, cluster_k=cluster_k, cluster_high=100.0,
        cluster_low=97.0, cluster_range_adr=0.99, line_ok=True, touch_zones=2,
        overshoot_adr=0.0, slope=-0.001, line_end=99.9, base_low=97.0,
        churn_l=churn_l, sma20_rising=sma20_rising, dryup=dryup,
    )


def test_every_dimension_hitting_is_the_four_and_a_half_star_ceiling():
    # The ceiling is 9 points, not 10: Base length is worth zero, so hitting it
    # buys nothing and the top of the scale is 4.5 stars.
    stars, breakdown = star_score(_det(), prior_move=True, sector_share=0.20)
    assert stars == 4.5
    assert len(breakdown) == len(DIMENSIONS) == 8
    assert all(d.hit for d in breakdown)
    assert sum(d.weight for d in breakdown) == 9


def test_the_permanent_half_star_floor():
    # Prior move fires for every detection by construction, so its one point is a
    # floor: a detection missing every other dimension still scores 0.5, never 0.
    stars, _ = star_score(
        _det(cluster_k=4, churn_l=0.10, base_len=20, sma20_rising=False,
             dryup=0.99, adr=0.04),
        prior_move=True, sector_share=0.05,
    )
    assert stars == 0.5


def test_adr_is_now_double_weighted_and_moves_a_full_star():
    # ADR was ×1, now ×2 — the sharpest selector in §5b (+29.4pp).
    base = dict(prior_move=True, sector_share=0.20)
    hit = star_score(_det(adr=0.06), **base)[0]
    miss = star_score(_det(adr=0.04), **base)[0]
    assert hit - miss == 1.0


def test_orderliness_is_now_single_weighted_and_moves_half_a_star():
    # Orderliness was ×2, now ×1 — he hits it less than the field (−9.1pp).
    base = dict(prior_move=True, sector_share=0.20)
    hit = star_score(_det(churn_l=0.45), **base)[0]
    miss = star_score(_det(churn_l=0.10), **base)[0]
    assert hit - miss == 0.5


def test_tightness_stays_double_weighted_and_moves_a_full_star():
    base = dict(prior_move=True, sector_share=0.20)
    with_tight = star_score(_det(cluster_k=5), **base)[0]
    without_tight = star_score(_det(cluster_k=4), **base)[0]
    assert with_tight - without_tight == 1.0


def test_base_length_is_weighted_zero_and_never_moves_the_score():
    # Zeroed on its −13.4pp wrong-way gap: it is measured, worth nothing, and
    # cannot change a star whether it hits or misses.
    base = dict(prior_move=True, sector_share=0.20)
    hit = star_score(_det(base_len=10), **base)[0]
    miss = star_score(_det(base_len=20), **base)[0]
    assert hit == miss


def test_base_length_keeps_a_visible_zero_weight_row():
    # The dimension stays in the breakdown at weight 0 — deleting it would make the
    # rubric look as though it never considered base length at all (PRD #138).
    _, breakdown = star_score(_det(), prior_move=True, sector_share=0.20)
    base_len_row = next(d for d in breakdown if d.dimension == "Base length")
    assert base_len_row.weight == 0


def test_the_thresholds_are_the_published_set():
    # Weights moved; the boolean thresholds did not. Each dimension awards on its
    # published boundary and denies just under it.
    def stars_with(**kw):
        return star_score(_det(**{k: v for k, v in kw.items() if k in
                                  ("cluster_k", "churn_l", "base_len",
                                   "sma20_rising", "dryup", "adr")}),
                          prior_move=kw.get("prior_move", True),
                          sector_share=kw.get("sector_share", 0.20))[0]

    all_hit = stars_with()
    assert all_hit == 4.5
    # cluster_k >= 5 (×2) ; dryup <= 0.95 (×1) ; adr >= 0.05 (×2)
    assert stars_with(cluster_k=4) == 3.5
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


def test_the_breakdown_names_all_eight_dimensions_with_their_recalibrated_weights():
    _, breakdown = star_score(_det(), prior_move=True, sector_share=0.2)
    names = [d.dimension for d in breakdown]
    assert names == [
        "Tightness", "Orderliness", "Prior move", "Base length",
        "MA support", "Volume", "Sector", "ADR",
    ]
    weights = {d.dimension: d.weight for d in breakdown}
    assert weights["Tightness"] == 2
    assert weights["ADR"] == 2
    assert weights["Orderliness"] == 1
    assert weights["Base length"] == 0
    assert weights["Prior move"] == weights["MA support"] == 1
    assert weights["Volume"] == weights["Sector"] == 1


def test_a_rubric_version_stamp_exists():
    # The stamp that lets a frozen digest star and a derived-on-read app star be
    # compared like with like (PRD #138).
    assert isinstance(RUBRIC_VERSION, int)
    assert RUBRIC_VERSION >= 2


def test_rubric_weights_carry_the_superseded_v1_alongside_the_live_v2():
    # The paired A2 re-run (#136) re-scores the *same* field under both rubrics so
    # a rubric change is separated from a field change. That needs the old (v1)
    # weights kept beside the live ones, keyed by version stamp.
    from screener.score import RUBRIC_WEIGHTS

    assert set(RUBRIC_WEIGHTS) >= {1, RUBRIC_VERSION}
    v1, v2 = RUBRIC_WEIGHTS[1], RUBRIC_WEIGHTS[RUBRIC_VERSION]
    # v1 is the ten-point rubric: Tightness/Orderliness ×2, everything else ×1.
    assert v1 == {
        "Tightness": 2, "Orderliness": 2, "Prior move": 1, "Base length": 1,
        "MA support": 1, "Volume": 1, "Sector": 1, "ADR": 1,
    }
    assert sum(v1.values()) == 10
    # v2 mirrors the live DIMENSIONS table, and totals nine.
    assert v2 == {name: weight for name, weight in DIMENSIONS}
    assert sum(v2.values()) == 9


def test_stars_under_rescore_a_breakdown_by_an_arbitrary_weight_map():
    # stars_under re-totals a breakdown's *hit booleans* under a supplied weight
    # map, so one field's detections can be scored under either rubric without
    # re-detecting. Under the live weights it reproduces star_score exactly.
    from screener.score import RUBRIC_WEIGHTS, stars_under

    det = _det(adr=0.06, churn_l=0.45, base_len=10)  # ADR + Orderliness + Base all hit
    stars, breakdown = star_score(det, prior_move=True, sector_share=0.20)
    assert stars_under(breakdown, RUBRIC_WEIGHTS[RUBRIC_VERSION]) == stars
    # Under v1 the same booleans score differently: ADR was ×1 not ×2, Orderliness
    # ×2 not ×1 (net 0), and Base length ×1 not ×0 (+1 point → +0.5 star).
    assert stars_under(breakdown, RUBRIC_WEIGHTS[1]) == stars + 0.5
