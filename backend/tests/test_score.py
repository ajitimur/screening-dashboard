"""The star score: eight boolean dimensions, ten weighted points (spec §4.7).

`points ÷ 2` = 0–5 stars. Booleans, not continuous, because the score is the
default sort of the only list in the app and a sort key you cannot audit is one
you will not trust. The score knows nothing about the stop and nothing about the
regime — every input below is a base signal, a rank percentile or a sector share.
"""

from datetime import date

from screener.detection import DETECTOR_VERSION, Detection
from screener.score import DIMENSIONS, star_score


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


def test_all_eight_dimensions_hit_is_a_perfect_five_stars():
    stars, breakdown = star_score(_det(), prior_move=True, sector_share=0.20)
    assert stars == 5.0
    assert len(breakdown) == len(DIMENSIONS) == 8
    assert all(d.hit for d in breakdown)
    # Ten weighted points: tightness and orderliness weigh 2, the other six weigh 1.
    assert sum(d.weight for d in breakdown) == 10


def test_no_dimension_hits_is_zero_stars():
    stars, breakdown = star_score(
        _det(cluster_k=4, churn_l=0.10, base_len=20, sma20_rising=False,
             dryup=0.99, adr=0.04),
        prior_move=False, sector_share=0.05,
    )
    assert stars == 0.0
    assert not any(d.hit for d in breakdown)


def test_the_two_double_weighted_dimensions_each_move_the_score_a_full_star():
    # Tightness and orderliness are ×2: flipping one alone is a full star (2 ÷ 2).
    base = dict(prior_move=True, sector_share=0.20)
    with_tight = star_score(_det(cluster_k=5), **base)[0]
    without_tight = star_score(_det(cluster_k=4), **base)[0]
    assert with_tight - without_tight == 1.0

    with_order = star_score(_det(churn_l=0.45), **base)[0]
    without_order = star_score(_det(churn_l=0.10), **base)[0]
    assert with_order - without_order == 1.0


def test_a_single_weighted_dimension_moves_the_score_half_a_star():
    base = dict(prior_move=True, sector_share=0.20)
    hit = star_score(_det(adr=0.06), **base)[0]
    miss = star_score(_det(adr=0.04), **base)[0]
    assert hit - miss == 0.5


def test_the_thresholds_are_the_published_set():
    # Each dimension awards on its published boundary and denies just under it.
    def stars_with(**kw):
        return star_score(_det(**{k: v for k, v in kw.items() if k in
                                  ("cluster_k", "churn_l", "base_len",
                                   "sma20_rising", "dryup", "adr")}),
                          prior_move=kw.get("prior_move", True),
                          sector_share=kw.get("sector_share", 0.20))[0]

    all_hit = stars_with()
    assert all_hit == 5.0
    # cluster_k >= 5 ; base_len <= 14 ; dryup <= 0.95 ; adr >= 0.05
    assert stars_with(cluster_k=4) == 4.0
    assert stars_with(base_len=15) == 4.5
    assert stars_with(dryup=0.96) == 4.5
    assert stars_with(adr=0.05) == 5.0          # inclusive at the boundary
    assert stars_with(adr=0.049) == 4.5
    # orderliness band 0.30 .. 0.60 inclusive; sector share >= 0.10
    assert stars_with(churn_l=0.30) == 5.0
    assert stars_with(churn_l=0.60) == 5.0
    assert stars_with(churn_l=0.61) == 4.0
    assert stars_with(sector_share=0.10) == 5.0
    assert stars_with(sector_share=0.09) == 4.5   # sector is ×1


def test_the_breakdown_names_all_eight_dimensions_with_their_weights():
    _, breakdown = star_score(_det(), prior_move=True, sector_share=0.2)
    names = [d.dimension for d in breakdown]
    assert names == [
        "Tightness", "Orderliness", "Prior move", "Base length",
        "MA support", "Volume", "Sector", "ADR",
    ]
    weights = {d.dimension: d.weight for d in breakdown}
    assert weights["Tightness"] == weights["Orderliness"] == 2
    assert all(weights[n] == 1 for n in names[2:])
