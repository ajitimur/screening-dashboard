"""The star score: eight boolean dimensions, ten weighted points (spec §4.7).

The sort key of the only list in the app. `points ÷ 2` = 0–5 stars, where
tightness and orderliness weigh 2 and the other six weigh 1 (max 10). **Booleans,
not continuous** (+0.255 vs +0.191 in the round that tested it): the score is the
default sort of the only list in the app, and a sort key you cannot audit is one
you will not trust (ticket 15 R4).

The eight dimensions and their **published** thresholds — one set serves both
markets (spec §4.7; the eye is harsher on IDX, but that is the population, not the
calibration):

| Dimension   | Weight | Rule                                    |
|-------------|--------|-----------------------------------------|
| Tightness   | ×2     | ``cluster_k >= 5``                      |
| Orderliness | ×2     | ``0.30 <= churn/L <= 0.60`` over the base |
| Prior move  | ×1     | decile percentile ``>= 0.90``           |
| Base length | ×1     | ``base_len <= 14``                      |
| MA support  | ×1     | ``SMA20`` rising, sign-only             |
| Volume      | ×1     | dry-up ``<= 0.95``                      |
| Sector      | ×1     | leave-one-out 1m sector share ``>= 0.10`` |
| ADR         | ×1     | ``ADR >= 0.05``                         |

Three of the eight are read off the detection's own signal vector (tightness,
base length, ADR); orderliness, MA support and volume are the detector's derived
signals (``churn_l``, ``sma20_rising``, ``dryup``); and two are **cross-sectional**
— the prior-move percentile and the leave-one-out sector share, supplied by the
caller from the same session's rank table and labels. All eight are booleans over
persisted quantities, so a corrected rubric replays backwards over history (spec
§7.5 / ticket 08 D16).

Two things this module deliberately does not take: **the stop** (``stopw_adr`` is
the cluster's range in ADR by identity, the narrowness the ×2 tightness dimension
already reads — one ruler, not two, §4.6) and **the regime** (advisory only,
§4.9). Neither is a parameter here, so the score cannot depend on either.

Pure and numpy-free, so it is unit-tested without the network.
"""

from __future__ import annotations

from dataclasses import dataclass

from .detection import Detection

# The published thresholds (spec §4.7). One set, both markets. An earlier
# wayfinding table carried different values under an objective later shown blind —
# these are the ones that stand.
# Prior move (decile percentile >= 0.90, ticket 06) has no constant here: it is
# not scored from the detection but passed in as a boolean by the caller, decided
# upstream by the decile gate. The rubric's ceiling — ten weighted points, ÷2 for
# 0–5 stars — is likewise not a tunable but the sum of the weights below.
TIGHT_K = 5              # cluster_k >= 5
CHURN_LO, CHURN_HI = 0.30, 0.60   # 0.30 <= churn/L <= 0.60, a band on both edges
BASE_LEN_MAX = 14        # base_len <= 14
DRYUP_MAX = 0.95         # dry-up <= 0.95
SECTOR_SHARE_MIN = 0.10  # leave-one-out 1m sector share >= 0.10, ticket 07
ADR_MIN = 0.05           # ADR >= 0.05


@dataclass(frozen=True)
class Dimension:
    """One row of the score breakdown: a named boolean and its weight. Eight of
    these reconstruct the star score arithmetically — weights, hits, ``n/10 →
    stars`` (spec §4.7 acceptance C4)."""

    dimension: str
    weight: int
    hit: bool


# The eight dimension labels and weights, in the spec's published order. The rule
# lives in :func:`star_score`; this is the fixed shape of every breakdown.
DIMENSIONS: tuple[tuple[str, int], ...] = (
    ("Tightness", 2),
    ("Orderliness", 2),
    ("Prior move", 1),
    ("Base length", 1),
    ("MA support", 1),
    ("Volume", 1),
    ("Sector", 1),
    ("ADR", 1),
)


def star_score(
    det: Detection, *, prior_move: bool, sector_share: float
) -> tuple[float, list[Dimension]]:
    """The 0–5 star score and its eight-row breakdown for one detection (§4.7).

    ``prior_move`` is whether the name clears the decile gate (percentile ≥ 0.90,
    ticket 06 — true for every detection by construction, so this dimension is
    fixed) and ``sector_share`` is its **leave-one-out** 1m sector share (ticket
    07); both are cross-sectional and computed by the caller off the session's
    rank table and labels. The other six dimensions read the detection's own
    signal vector — never the stop, never the regime.

    Returns ``(stars, breakdown)`` where ``stars`` is ``points ÷ 2`` and
    ``breakdown`` is the eight :class:`Dimension` rows in published order.
    """
    hits = {
        "Tightness": det.cluster_k >= TIGHT_K,
        "Orderliness": CHURN_LO <= det.churn_l <= CHURN_HI,
        "Prior move": prior_move,
        "Base length": det.base_len <= BASE_LEN_MAX,
        "MA support": det.sma20_rising,
        "Volume": det.dryup <= DRYUP_MAX,
        "Sector": sector_share >= SECTOR_SHARE_MIN,
        "ADR": det.adr >= ADR_MIN,
    }
    breakdown = [Dimension(name, weight, hits[name]) for name, weight in DIMENSIONS]
    points = sum(d.weight for d in breakdown if d.hit)
    return points / 2, breakdown
