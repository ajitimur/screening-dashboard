"""The star score: eight dimensions — seven boolean, one banded — nine weighted
points (spec §4.7, recalibrated by PRD #138, Tightness graded by #145/#154).

The sort key of the only list in the app. `points ÷ 2` = stars, with a **real
range of 0.5–4.5, never 0–5**: ``Prior move`` fires for every detection by
construction (a permanent half-star floor) and ``Base length`` is weighted zero
(the ninth point can never be earned). The scale was never truly 0–5; the ×0
makes that visible rather than nominal. **Auditable, not continuous** (+0.255 vs
+0.191 in the round that tested a fully continuous score): the score is the default
sort of the only list in the app, and a sort key you cannot audit is one you will
not trust (ticket 15 R4). v3's one graded dimension is banded to integral points for
that reason — a breakdown still reconstructs the star by addition, and the
nine-point ceiling and the ``÷ 2`` are untouched.

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
| Tightness   | ×2     | graded on ``range_3bar_adr``: 2 ≤ 1.0, 1 ≤ 2.0, else 0 |
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

**Tightness is the one dimension that is not a boolean (v3, #145/#154).** Findings
§3b measured mean R by three-bar range across his executed trades and found a
*smooth monotone decline with no feature anywhere* — +2.02 / +1.35 / +0.84 / +0.35 /
−0.36 R across the range — so a threshold is the wrong shape for it, in the same
sense that #143's entry-to-MA cliff made a threshold the right shape there. v3 grades
it in bands off :data:`Detection.range_3bar_adr` (see :data:`TIGHTNESS_BANDS`), and
:class:`Rubric` — not the stored row — owns the mapping, so v2 still re-scores a v3
row exactly. What licenses replacing a threshold with a grade, and why that is not
the loosening ADR 0002 forbids, is
``docs/adr/0004-replacing-a-threshold-with-a-graded-input.md`` — the argument is
recorded there rather than made here.

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
from dataclasses import dataclass, field

from .detection import Detection

# The rubric version stamp (PRD #138). Version 1 was the ten-point rubric
# (Tightness/Orderliness ×2, all else ×1); version 2 was the nine-point
# selection-recalibrated one, boolean throughout; version 3 keeps v2's weights and
# grades ``Tightness`` off the row's own three-bar range (#145/#154). Stars are
# derived on read *except in a
# digest*, which freezes them — so without a stamp a changed rubric leaves last
# week's digest and today's app disagreeing about the same session with nothing
# recording why. It is also what lets a paired re-run (#136) compare like with
# like instead of comparing two rubrics while believing it compares two fields.
RUBRIC_VERSION = 3

# The published thresholds (spec §4.7). One set, both markets. An earlier
# wayfinding table carried different values under an objective later shown blind —
# these are the ones that stand.
# Prior move (decile percentile >= 0.90, ticket 06) has no constant here: it is
# not scored from the detection but passed in as a boolean by the caller, decided
# upstream by the decile gate. The rubric's ceiling — nine weighted points, ÷2 for
# 0.5–4.5 stars — is likewise not a tunable but the sum of the weights below.
TIGHT_K = 5              # cluster_k >= 5 — v1/v2's Tightness rule, still recorded
# v3's Tightness bands: ``(upper bound in ADR, points)``, ascending, first match
# wins, nothing beyond the last. Read off :data:`Detection.range_3bar_adr` — the
# *ungated* base tightness, which is the quantity findings §3b's outcome table is
# denominated in and the one the far-outlier guard tests.
#
# **The edges are §3b's own bucket boundaries, not new numbers.** That table
# reports mean R by three-bar range at 0.0–1.0 (+2.02), 1.0–1.5 (+1.35), 1.5–2.0
# (+0.84), 2.0–3.0 (+0.35) and 3.0+ (−0.36); the bands collapse it to the two
# places expectancy roughly halves. ADR 0001's constraint holds — the *ordering*
# of the buckets licenses the direction, and no band edge reads a gap's magnitude.
#
# **Bands, not a fraction.** Integral points keep the nine-point ceiling and the
# ``points ÷ 2 → stars`` arithmetic exactly as they were, so no star display,
# frozen digest or acceptance metric changes shape. A fractional grade would move
# every one of those for a resolution the evidence (five buckets, the thinnest
# n = 10) cannot support.
TIGHTNESS_BANDS: tuple[tuple[float, int], ...] = ((1.0, 2), (2.0, 1))
CHURN_LO, CHURN_HI = 0.30, 0.60   # 0.30 <= churn/L <= 0.60, a band on both edges
BASE_LEN_MAX = 14        # base_len <= 14
DRYUP_MAX = 0.95         # dry-up <= 0.95
SECTOR_SHARE_MIN = 0.10  # leave-one-out 1m sector share >= 0.10, ticket 07
ADR_MIN = 0.05           # ADR >= 0.05


@dataclass(frozen=True)
class Dimension:
    """One row of the score breakdown: a named boolean, its weight, and — for a
    graded dimension — the value that was graded. Eight of these reconstruct the
    star score arithmetically (spec §4.7 acceptance C4; nine-point ceiling, PRD
    #138).

    **The row carries the value, never the verdict of a particular rubric** (#154).
    ``hit`` is the boolean the *setup* has — for ``Tightness`` that is still v1/v2's
    ``cluster_k >= TIGHT_K``, which no value can reconstruct — and ``value`` is the
    quantity a graded rubric maps to points. Both are properties of the setup, so
    the invariant :func:`stars_under` rests on survives grading: only the mapping
    moves between versions, and a v2 re-score of a v3 row is exact rather than
    approximate. Bake a v3 grade into ``hit`` instead and the paired A2 re-run
    (#136) would be comparing two rubrics while believing it compares two fields.

    ``value`` is ``None`` on the seven ungraded dimensions, and on any breakdown
    written before the field existed.
    """

    dimension: str
    weight: int
    hit: bool
    value: float | None = None


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


@dataclass(frozen=True)
class Rubric:
    """One version's mapping from a breakdown row to points.

    ``weights`` is the per-dimension weight — for a graded dimension, the points a
    row can earn at most. ``bands`` names the dimensions this version *grades*,
    each with its ascending ``(upper bound, points)`` table; every other dimension
    scores ``weight`` when it hits and nothing when it does not.

    A rubric owns its own value → points mapping, which is what lets a graded
    dimension coexist with a stored breakdown replayable under any version: the row
    carries the value, the rubric decides what it is worth (#154).
    """

    weights: Mapping[str, int]
    bands: Mapping[str, tuple[tuple[float, int], ...]] = field(default_factory=dict)

    def points(self, row: Dimension) -> int:
        """What ``row`` is worth under this rubric.

        A graded dimension whose row carries no ``value`` falls back to the
        boolean — a breakdown written before the value existed, or one the replay
        struck a dimension from, still re-totals rather than silently scoring zero.
        """
        bands = self.bands.get(row.dimension)
        if bands is None or row.value is None:
            return self.weights.get(row.dimension, 0) if row.hit else 0
        for upper, points in bands:
            if row.value <= upper:
                return points
        return 0


# Every rubric version, keyed by its :data:`RUBRIC_VERSION` stamp, so a stored
# breakdown can be re-scored under any version without re-detecting. Version 1 is
# the superseded ten-point rubric (Tightness and Orderliness ×2, everything else
# ×1); version 2 the nine-point selection-recalibrated one, boolean throughout;
# version 3 the live one — v2's weights exactly, with ``Tightness`` graded off the
# row's three-bar range. The superseded versions are kept beside the live one
# specifically for the paired A2 re-run (#136), which scores one field under every
# rubric so a *rubric* change is separated from a *field* change instead of the two
# moving at once. **Adding a version must never edit an older one**: v2 below is
# what shipped, and a re-score under it has to reproduce what shipped.
RUBRICS: Mapping[int, Rubric] = {
    1: Rubric({
        "Tightness": 2,
        "Orderliness": 2,
        "Prior move": 1,
        "Base length": 1,
        "MA support": 1,
        "Volume": 1,
        "Sector": 1,
        "ADR": 1,
    }),
    # Spelled out, not derived from DIMENSIONS. A superseded version must record
    # what *shipped*, and a table computed from the live one silently follows any
    # future weight edit — which would corrupt the paired re-run in the one way it
    # cannot detect, by moving the "before" as well as the "after".
    2: Rubric({
        "Tightness": 2,
        "Orderliness": 1,
        "Prior move": 1,
        "Base length": 0,
        "MA support": 1,
        "Volume": 1,
        "Sector": 1,
        "ADR": 2,
    }),
    # The live one *is* derived from DIMENSIONS: there is one live weight table and
    # this must not be a second copy of it.
    RUBRIC_VERSION: Rubric(
        {name: weight for name, weight in DIMENSIONS},
        bands={"Tightness": TIGHTNESS_BANDS},
    ),
}


def stars_under(breakdown: Iterable[Dimension], rubric: Rubric) -> float:
    """Re-total a stored breakdown under an arbitrary rubric → stars.

    A breakdown row records what the *setup* is — the boolean it satisfies and, on
    a graded dimension, the value it carries — never what a particular rubric made
    of it. Only the mapping moves between versions. So one field's detections can
    be scored under any rubric (:data:`RUBRICS`) from the same breakdown, which is
    what lets the paired A2 re-run (#136) hold the field fixed while swapping only
    the rubric. Under the live rubric it reproduces :func:`star_score` exactly
    (``points ÷ 2``); a dimension the rubric does not weigh scores nothing.
    Sector-struck breakdowns from the replay (:mod:`replay.field`) re-total
    correctly because the sum ranges over the rows that are present.
    """
    return sum(rubric.points(d) for d in breakdown) / 2


def live_points(row: Dimension) -> int:
    """What one breakdown row earns under the **live** rubric.

    The one thing a stored row deliberately does not carry (#154), published on the
    API payload beside its ``rubric_version`` so a client can reconstruct the star
    by addition without owning a copy of the band table. Since v3 the old
    arithmetic — ``weight where hit`` — no longer totals a graded breakdown, and a
    sort key you cannot audit is one you will not trust.
    """
    return RUBRICS[RUBRIC_VERSION].points(row)


def star_score(
    det: Detection,
    *,
    prior_move: bool,
    sector_share: float,
    rs_line: bool = False,
) -> tuple[float, list[Dimension]]:
    """The star score (0.5–4.5) and its eight-row breakdown for one detection (§4.7).

    ``prior_move`` is whether the name clears the decile gate (percentile ≥ 0.90,
    ticket 06 — true for every detection by construction, so this dimension is
    fixed) and ``sector_share`` is its **leave-one-out** 1m sector share (ticket
    07); both are cross-sectional and computed by the caller off the session's
    rank table and labels. The other six dimensions read the detection's own
    signal vector — never the stop, never the regime.

    ``rs_line`` is the third caller-supplied cross-sectional input and the one
    dimension **under measurement**: whether the name held its ratio to the market
    index across its own base (:mod:`screener.relative_strength`, #160). It is
    accepted here and **deliberately not scored** — no :data:`DIMENSIONS` row, no
    weight, no effect on the returned stars or breakdown. The wiring lands ahead of
    the evidence so that #161 can admit the dimension by editing the rubric alone,
    and so that the four ship criteria pre-registered in ADR 0005 decide the
    question rather than the convenience of the code. If the study returns
    *do not ship*, this parameter comes out with it.

    Returns ``(stars, breakdown)`` where ``stars`` is ``points ÷ 2`` and
    ``breakdown`` is the eight :class:`Dimension` rows in published order. The
    totalling is :func:`stars_under` under the live weights — one site owns the
    ``÷ 2``, so the live rubric cannot drift from the version table it is keyed in.
    """
    # Named, documented, and read by nothing: the rubric is unchanged until #160's
    # verdict lands. Referenced here so the staging is explicit rather than looking
    # like an argument that was forgotten.
    del rs_line
    # ``Tightness`` is the one graded dimension (#154): its row carries the
    # *value* — the ungated three-bar range — and the live rubric bands it, while
    # ``hit`` keeps v1/v2's ``cluster_k >= TIGHT_K`` so those versions still
    # re-score the same row exactly.
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
    values = {"Tightness": det.range_3bar_adr}
    breakdown = [
        Dimension(name, weight, hits[name], values.get(name))
        for name, weight in DIMENSIONS
    ]
    return stars_under(breakdown, RUBRICS[RUBRIC_VERSION]), breakdown
