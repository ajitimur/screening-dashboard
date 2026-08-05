"""Sector strength, rotation and the ranked-industry board (spec §4.4).

This is the second reader of the shared rank table (§4.3), and it defines no new
notion of "strong": a name is strong in a lookback iff it is in that lookback's
top decile, exactly as :mod:`screener.ranks` computes it. Everything here is an
*aggregation* of those decile memberships up to the sector and industry axes
(ticket 07 S2, R6).

The quantities, each fixed by ticket 07:

- **Sector strength** = the share of a sector's members in that lookback's top
  decile, five numbers per sector (``1w/1m/3m/6m/12m``). ``k/n`` where ``k`` is
  the sector's decile members and ``n`` is the sector's universe count. Per
  lookback deciles make **10% the fair share** by construction, so 25–30% is
  visibly leading and 0% visibly dead (S2). An index return was rejected — a
  sector with 8 of 40 names ripping and 32 flat has a mediocre index return and
  is exactly the sector to surface (S2).
- **Rotation** is two columns, not a sparkline (S3): the **shape differential**
  ``share(1w) − share(6m)`` (the default sort) and the **temporal delta**
  ``share(1m, tonight) − share(1m, 20 sessions ago)``.
- **The quantization guard is not optional** (S4). One name moves an IDX sector's
  share by up to 10pp; on US 0.3–1.7pp. So a sector needs ``k ≥ 2`` in the
  shorter lookback (1w) to top the rotation board — single-name sectors sort into
  a separate visible group below, numbers intact — and every row carries ``k/n``.
  The Δ20d cell is marked low-confidence where its own lookback (1m) rests on
  fewer than two names.
- **An industry is ranked only at ``n ≥ 10``** (S5) — one rule, both markets. 10
  is derived, not picked: the point at which one name can move the share by at
  most 10pp, the decile baseline itself.

All 11 sectors always render, even at 0% on every lookback (S8). Pure over rank
rows and a ``symbol → label`` mapping; the store-driven read lives in the app.
"""

from __future__ import annotations

from .indicators import LOOKBACKS
from .models import IndustryStrength, SectorStrength
from .ranks import TOP_DECILE, Rank

# The 11 Morningstar GECS sectors, the same taxonomy on both markets (spec §2,
# ticket 03). Always rendered in full — a dead sector is information (S8).
SECTORS: tuple[str, ...] = (
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
)

# The shape differential's two lookbacks (S3): rotating in = strong short, weak long.
SHORT_LOOKBACK = "1w"
LONG_LOOKBACK = "6m"

# The temporal delta is measured on the 1m lookback, tonight vs 20 sessions ago —
# the 20 inherited from the swing horizon, not invented (S3).
TEMPORAL_LOOKBACK = "1m"
TEMPORAL_SESSIONS = 20

# ``k ≥ 2`` in the shorter lookback to top the rotation board — one stock is not a
# sector rotating (S4). Also the low-confidence threshold on the Δ20d column.
ROTATION_MIN_MEMBERS = 2

# An industry is ranked only at ``n ≥ 10`` members (S5): the point at which one
# name moves the share by at most 10pp, the decile baseline itself.
INDUSTRY_MIN_MEMBERS = 10


def _aggregate(
    rows: list[Rank], label_of: dict[str, str]
) -> tuple[dict[str, set[str]], dict[str, dict[str, set[str]]]]:
    """Fold rank rows up to a label axis (sector or industry).

    Returns ``(members, decile)`` where ``members[label]`` is every symbol
    carrying that label that appears in *any* lookback — a universe member has at
    least a 1w row, so this is the ``n`` denominator — and
    ``decile[label][lookback]`` is the symbols in that lookback's top decile. A
    symbol with no label (never fetched, or a failed fetch) contributes to
    neither: it cannot be placed on the axis (spec §3.3).
    """
    members: dict[str, set[str]] = {}
    decile: dict[str, dict[str, set[str]]] = {}
    for r in rows:
        label = label_of.get(r.symbol)
        if not label:
            continue
        members.setdefault(label, set()).add(r.symbol)
        if r.percentile >= TOP_DECILE:
            decile.setdefault(label, {}).setdefault(r.lookback, set()).add(r.symbol)
    return members, decile


def _k(decile: dict[str, dict[str, set[str]]], label: str, lookback: str) -> int:
    return len(decile.get(label, {}).get(lookback, ()))


def _shares(
    decile: dict[str, dict[str, set[str]]], label: str, n: int
) -> tuple[dict[str, float], dict[str, int]]:
    """The five per-lookback ``(share, k)`` for one label. ``share = k/n``, and 0
    when the label has no members (a sector that always renders at 0%, S8)."""
    counts = {lb: _k(decile, label, lb) for lb in LOOKBACKS}
    shares = {lb: (counts[lb] / n if n else 0.0) for lb in LOOKBACKS}
    return shares, counts


def sector_strengths(
    rows: list[Rank],
    sector_of: dict[str, str],
    *,
    past_rows: list[Rank] | None = None,
) -> list[SectorStrength]:
    """The 11-sector board for one session (spec §4.4 / ticket 07 S2–S8).

    ``rows`` is tonight's rank table; ``sector_of`` maps each member to its GECS
    sector. All 11 sectors are emitted, even at 0% (S8). When ``past_rows`` (the
    rank table from :data:`TEMPORAL_SESSIONS` sessions ago) is given, each row
    also carries its temporal delta; otherwise the delta is ``None`` — there is
    not yet 20 sessions of history to difference against.

    Default sort is the shape differential descending, with the
    rotation-ineligible sectors (``k(1w) < 2``) grouped *below* the eligible ones
    so a thin single-name sector can never top the board (S4).
    """
    members, decile = _aggregate(rows, sector_of)
    past_members, past_decile = (
        _aggregate(past_rows, sector_of) if past_rows is not None else ({}, {})
    )

    out: list[SectorStrength] = []
    for sector in SECTORS:
        n = len(members.get(sector, ()))
        shares, counts = _shares(decile, sector, n)
        temporal: float | None = None
        if past_rows is not None:
            past_n = len(past_members.get(sector, ()))
            past_share = _k(past_decile, sector, TEMPORAL_LOOKBACK) / past_n if past_n else 0.0
            temporal = shares[TEMPORAL_LOOKBACK] - past_share
        out.append(
            SectorStrength(
                sector=sector,
                members=n,
                shares=shares,
                decile_counts=counts,
                shape_differential=shares[SHORT_LOOKBACK] - shares[LONG_LOOKBACK],
                temporal_delta=temporal,
                rotation_eligible=counts[SHORT_LOOKBACK] >= ROTATION_MIN_MEMBERS,
                delta_low_confidence=counts[TEMPORAL_LOOKBACK] < ROTATION_MIN_MEMBERS,
            )
        )
    # Ineligible sectors sort into the group below; within each group, shape
    # differential descending. SECTORS order breaks any remaining tie.
    out.sort(key=lambda s: (not s.rotation_eligible, -s.shape_differential))
    return out


def industry_strengths(
    rows: list[Rank],
    industry_of: dict[str, str],
    sector_of: dict[str, str],
    *,
    min_members: int = INDUSTRY_MIN_MEMBERS,
) -> list[IndustryStrength]:
    """The ranked-industry board: only industries with ``≥ min_members`` (S5).

    One rule on both markets — it yields many US rows and few IDX ones (parity of
    rule, not of result). Industries below the floor are not returned here; they
    remain the per-candidate tag elsewhere. Sorted by shape differential
    descending, the same default as the sector board.
    """
    members, decile = _aggregate(rows, industry_of)
    out: list[IndustryStrength] = []
    for industry, symbols in members.items():
        n = len(symbols)
        if n < min_members:
            continue
        shares, counts = _shares(decile, industry, n)
        # Every member of an industry shares its sector by taxonomy; take any.
        sector = next((sector_of.get(s, "") for s in symbols if sector_of.get(s)), "")
        out.append(
            IndustryStrength(
                industry=industry,
                sector=sector,
                members=n,
                shares=shares,
                decile_counts=counts,
                shape_differential=shares[SHORT_LOOKBACK] - shares[LONG_LOOKBACK],
            )
        )
    out.sort(key=lambda i: (-i.shape_differential, i.industry))
    return out
