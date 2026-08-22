"""The star score: eight boolean dimensions, nine weighted points (spec §4.7,
recalibrated by PRD #138).

The sort key of the only list in the app. `points ÷ 2` = stars, with a **real
range of 0.5–4.5, never 0–5**: ``Prior move`` fires for every detection by
construction (a permanent half-star floor) and ``Base length`` is weighted zero
(the ninth point can never be earned). The scale was never truly 0–5; the ×0
makes that visible rather than nominal. **Booleans, not continuous** (+0.255 vs
+0.191 in the round that tested it): the score is the default sort of the only
list in the app, and a sort key you cannot audit is one you will not trust
(ticket 15 R4).

**What the weights encode** (ADR 0001): the method's *revealed selection*,
evidenced by Kullamägi's executed trades — the §5b selection contrast of 69 taken
against 14,354 not-taken detections. The replay licenses the **direction** of a
weight, from the *ordering* of the measured selection gaps; nothing here reads a
gap's value, because the signs survive the field's 29% coverage hole and the
magnitudes do not (#128 Q2). PRD #138 moved four weights off that ordering; the
three-weight ordinal swap below (ADR up, Orderliness and Base length down) is the
one ticketed as #135:

- **ADR ×1 → ×2** — the sharpest selector in the rubric (+29.4pp). [#135]
- **Orderliness ×2 → ×1** — he hits it *less* than the field he passed over (−9.1pp). [#135]
- **Base length ×1 → ×0** — the largest wrong-way gap of any dimension (−13.4pp). [#135]
  ``BASE_LEN_MAX = 14`` is the named suspect and is left open: the ×0 says the
  dimension *as specified* earns nothing, not that base length is irrelevant.
- Tightness stays ×2 (+20.8pp, second-strongest); Prior move / MA support /
  Volume / Sector stay ×1, having no ordinal basis to move (see the table below).

The eight dimensions and their **published** thresholds — one set serves both
markets (spec §4.7; the eye is harsher on IDX, but that is the population, not the
calibration; a weight *ordering* is shape not magnitude, so §8 permits it
travelling to IDX):

| Dimension   | Weight | Rule                                    |
|-------------|--------|-----------------------------------------|
| Tightness   | ×2     | ``cluster_k >= 5``                      |
| Orderliness | ×1     | ``0.30 <= churn/L <= 0.60`` over the base |
| Prior move  | ×1     | decile percentile ``>= 0.90`` (constant) |
| Base length | ×0     | ``base_len <= 14`` (measured, worth nothing) |
| MA support  | ×1     | ``SMA20`` rising, sign-only             |
| Volume      | ×1     | dry-up ``<= 0.95``                      |
| Sector      | ×1     | leave-one-out 1m sector share ``>= 0.10`` |
| ADR         | ×2     | ``ADR >= 0.05``                         |

``Tightness`` here is **base tightness** — how quiet the stock was before the break,
read off the cluster's geometry. It is not stop width, and the two are 3.8× apart on
his own trades (findings §3b, issue #147); the dimension label is kept as published
because it rides the API payload and the digest.

Three of the eight are read off the detection's own signal vector (base tightness,
base length, ADR); orderliness, MA support and volume are the detector's derived
signals (``churn_l``, ``sma20_rising``, ``dryup``); and two are **cross-sectional**
— the prior-move percentile and the leave-one-out sector share, supplied by the
caller from the same session's rank table and labels. All eight are booleans over
persisted quantities, so a corrected rubric replays backwards over history (spec
§7.5 / ticket 08 D16).

Two things this module deliberately does not take: **the stop** and **the regime**
(advisory only, §4.9). Neither is a parameter here, so the score cannot depend on
either. The stop was originally excluded as a duplicate ruler — ``stopw_adr`` was
then the cluster-low distance, so scoring it would have re-read the same base
tightness the ×2 dimension already reads (§4.6). Since #127 it is the trader's
**stop width** convention, a constant 0.345 ADR on every row, so it now carries no
cross-sectional signal at all. Different reason, same exclusion.

Pure and numpy-free, so it is unit-tested without the network.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .detection import Detection

# The rubric version stamp (PRD #138). Version 1 was the ten-point rubric
# (Tightness/Orderliness ×2, all else ×1); version 2 is the nine-point
# selection-recalibrated rubric below. Stars are derived on read *except in a
# digest*, which freezes them — so without a stamp a changed rubric leaves last
# week's digest and today's app disagreeing about the same session with nothing
# recording why. It is also what lets a paired re-run (#136) compare like with
# like instead of comparing two rubrics while believing it compares two fields.
RUBRIC_VERSION = 2

# The published thresholds (spec §4.7). One set, both markets. An earlier
# wayfinding table carried different values under an objective later shown blind —
# these are the ones that stand.
# Prior move (decile percentile >= 0.90, ticket 06) has no constant here: it is
# not scored from the detection but passed in as a boolean by the caller, decided
# upstream by the decile gate. The rubric's ceiling — nine weighted points, ÷2 for
# 0.5–4.5 stars — is likewise not a tunable but the sum of the weights below.
TIGHT_K = 5              # cluster_k >= 5 — base tightness, never a stop width
CHURN_LO, CHURN_HI = 0.30, 0.60   # 0.30 <= churn/L <= 0.60, a band on both edges
BASE_LEN_MAX = 14        # base_len <= 14
DRYUP_MAX = 0.95         # dry-up <= 0.95
SECTOR_SHARE_MIN = 0.10  # leave-one-out 1m sector share >= 0.10, ticket 07
ADR_MIN = 0.05           # ADR >= 0.05


@dataclass(frozen=True)
class Dimension:
    """One row of the score breakdown: a named boolean and its weight. Eight of
    these reconstruct the star score arithmetically — weights, hits, ``n/9 →
    stars`` (spec §4.7 acceptance C4; nine-point ceiling, PRD #138)."""

    dimension: str
    weight: int
    hit: bool


# The eight dimension labels and weights, in the spec's published order. The rule
# lives in :func:`star_score`; this is the fixed shape of every breakdown.
DIMENSIONS: tuple[tuple[str, int], ...] = (
    ("Tightness", 2),
    ("Orderliness", 1),
    ("Prior move", 1),
    ("Base length", 0),
    ("MA support", 1),
    ("Volume", 1),
    ("Sector", 1),
    ("ADR", 2),
)


# The weight of every rubric version, keyed by its :data:`RUBRIC_VERSION` stamp,
# so a set of *hit booleans* can be re-scored under any version without
# re-detecting. Version 1 is the superseded ten-point rubric (Tightness and
# Orderliness ×2, everything else ×1); version 2 is the live nine-point table
# above. Kept beside the live one specifically for the paired A2 re-run (#136),
# which scores one field under both rubrics so a *rubric* change is separated from
# a *field* change instead of the two moving at once.
RUBRIC_WEIGHTS: Mapping[int, Mapping[str, int]] = {
    1: {
        "Tightness": 2,
        "Orderliness": 2,
        "Prior move": 1,
        "Base length": 1,
        "MA support": 1,
        "Volume": 1,
        "Sector": 1,
        "ADR": 1,
    },
    RUBRIC_VERSION: {name: weight for name, weight in DIMENSIONS},
}


def stars_under(breakdown: Iterable[Dimension], weights: Mapping[str, int]) -> float:
    """Re-total a breakdown's hit booleans under an arbitrary weight map → stars.

    The hits are a property of the *setup*, not the rubric — only the weights move
    between versions. So one field's detections can be scored under either rubric
    (:data:`RUBRIC_WEIGHTS`) from the same breakdown, which is what lets the paired
    A2 re-run (#136) hold the field fixed while swapping only the weights. Under the
    live weights it reproduces :func:`star_score` exactly (``points ÷ 2``); a
    dimension absent from ``weights`` scores nothing. Sector-struck breakdowns from
    the replay (:mod:`replay.field`) re-total correctly because the sum ranges over
    the rows that are present.
    """
    points = sum(weights.get(d.dimension, 0) for d in breakdown if d.hit)
    return points / 2


def star_score(
    det: Detection, *, prior_move: bool, sector_share: float
) -> tuple[float, list[Dimension]]:
    """The star score (0.5–4.5) and its eight-row breakdown for one detection (§4.7).

    ``prior_move`` is whether the name clears the decile gate (percentile ≥ 0.90,
    ticket 06 — true for every detection by construction, so this dimension is
    fixed) and ``sector_share`` is its **leave-one-out** 1m sector share (ticket
    07); both are cross-sectional and computed by the caller off the session's
    rank table and labels. The other six dimensions read the detection's own
    signal vector — never the stop, never the regime.

    Returns ``(stars, breakdown)`` where ``stars`` is ``points ÷ 2`` and
    ``breakdown`` is the eight :class:`Dimension` rows in published order. The
    totalling is :func:`stars_under` under the live weights — one site owns the
    ``÷ 2``, so the live rubric cannot drift from the version table it is keyed in.
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
    return stars_under(breakdown, RUBRIC_WEIGHTS[RUBRIC_VERSION]), breakdown
