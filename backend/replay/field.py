"""A2, the replayed field: detections, candidates and the seven-dimension star
score, per session, over the forward chain (PRD #114 "A2 replay chain" / "Star
score in replay", issue #118).

Where :mod:`replay.chain` rebuilt universe membership and ranks session by
session (#117), this lands the rest of the field on top of it: for each measured
session the study runs the app's detector over that session's universe, gated on
the detection lookbacks' deciles, builds the candidates and derives a **star
score** for each — all with the app's own functions, unmodified (user story 31).

**Seven of eight dimensions.** The sector dimension is dropped outright, because
the labels table is the store's one in-place write and carries no history, so a
symbol's sector in 2020 is unrecoverable (PRD "Star score in replay"). No work is
done to date the labels table — the dimension is dropped, not repaired. The
replayed score therefore totals **nine** weighted points, not ten, and is always
labelled a :data:`SEVEN_DIM_LABEL` so it can never be confused with the app's own
ten-point score. The labels table is never read: a dummy sector share is handed
to :func:`screener.score.star_score`, and the one row it decides is discarded.

**Not-taken detections.** Every member of the field on a session where a trade
was entered elsewhere is a *not-taken detection* (PRD user story 25). These are a
comparison group for A3's selection contrast, never a negative label — he may
never have seen them, so they record no rejection. They are flagged per session
here so a later ticket can identify them without re-deriving the field.

**Coverage.** Every field-derived output carries a coverage number against the
committed blind-spot tickers for its scope (user story 22): a ranking result is
never read without knowing how much of the field was missing. The count rides on
every :class:`FieldSession`, inherited from the chain's :class:`SessionField`.

Nothing here touches the live store: the field reads and writes only the
purpose-built replay store handed to it (user story 28).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from screener.detection import Detection, detection_gate
from screener.pipeline import rebuild_detections
from screener.ranks import Rank
from screener.score import Dimension, star_score
from screener.store import Store

from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, replay_chain
from .reference import ExecutedTrade

# The sector dimension, dropped from the replayed score (PRD "Star score in
# replay"). Named so :func:`seven_dimension_score` strikes exactly the app's
# sector row and nothing else.
SECTOR_DIMENSION = "Sector"

# Ten weighted points minus the dropped sector dimension's one. The replayed
# score always totals out of nine, and is always labelled a seven-dimension score
# so it is never confused with the app's ten-point score.
SEVEN_DIM_MAX_POINTS = 9
SEVEN_DIM_LABEL = "seven-dimension score"


@dataclass(frozen=True)
class SevenDimScore:
    """The replayed star score for one detection — seven of eight dimensions.

    ``points`` is the weighted points hit, out of :data:`SEVEN_DIM_MAX_POINTS`
    (nine); ``stars`` is ``points / 2``. ``breakdown`` is the seven surviving
    :class:`screener.score.Dimension` rows in the app's published order, the
    sector row absent. ``label`` is :data:`SEVEN_DIM_LABEL` on every emitted
    score, so the replayed figure is never mistaken for the app's ten-point one.
    """

    stars: float
    points: int
    max_points: int
    breakdown: list[Dimension]
    label: str


def seven_dimension_score(det: Detection, *, prior_move: bool) -> SevenDimScore:
    """The seven-dimension replayed star score for one detection.

    Reuses the app's own :func:`screener.score.star_score` unmodified (user story
    31) and strikes the sector row from its breakdown. The labels table is never
    read: a dummy ``sector_share`` is passed and the sector row it decides is
    discarded, so the score cannot depend on a sector it could not recover. The
    surviving seven dimensions are re-totalled out of nine.
    """
    _stars, breakdown = star_score(det, prior_move=prior_move, sector_share=0.0)
    kept = [d for d in breakdown if d.dimension != SECTOR_DIMENSION]
    points = sum(d.weight for d in kept if d.hit)
    return SevenDimScore(
        stars=points / 2,
        points=points,
        max_points=SEVEN_DIM_MAX_POINTS,
        breakdown=kept,
        label=SEVEN_DIM_LABEL,
    )


@dataclass(frozen=True)
class ScoredDetection:
    """One candidate in the replayed field: a detection with its star score.

    ``star_rank`` is the 1-based position in star order (score descending, the
    app's candidate order). ``not_taken`` marks a field member on a session where
    an executed trade was entered elsewhere — a comparison-group member, never a
    rejection (PRD user story 25). ``taken`` is its mirror: the field member whose
    own name *was* the executed trade entered this session — his actual pick,
    against which the not-taken detections are contrasted (A3 selection contrast,
    issue #122). A quiet session (no entry) leaves both false.
    """

    symbol: str
    detection: Detection
    score: SevenDimScore
    star_rank: int
    not_taken: bool
    taken: bool = False


@dataclass(frozen=True)
class FieldSession:
    """One session's replayed field: its universe members, the star-ranked
    candidates, and the coverage against the blind-spot tickers.

    ``detections`` is the field in star order, highest score first. ``members`` is
    the session's whole universe (a member need not sit in a base). ``blind_spot_count``
    is the coverage figure every field-derived output must carry (user story 22),
    inherited from the chain's :class:`replay.chain.SessionField`.
    """

    session: date
    burn_in: bool
    members: list[str]
    detections: list[ScoredDetection]
    blind_spot_count: int

    @property
    def field_size(self) -> int:
        """How many candidates the field carried this session."""
        return len(self.detections)

    @property
    def not_taken(self) -> list[ScoredDetection]:
        """The not-taken detections — the session's comparison group (§25)."""
        return [d for d in self.detections if d.not_taken]

    @property
    def taken(self) -> list[ScoredDetection]:
        """The taken detections — the field members he actually entered here (#122)."""
        return [d for d in self.detections if d.taken]


def build_field(
    detections: list[Detection],
    ranks: list[Rank],
    *,
    entered: Iterable[str] = (),
    any_entry: bool = False,
) -> list[ScoredDetection]:
    """Score each detection and sort into star order — the replayed candidate list.

    ``ranks`` is the session's rank table, read only for the prior-move decile gate
    (every detection clears it by construction, but computed honestly off the same
    table the app's list uses, never assumed). The order is the app's candidate
    order (:mod:`screener.candidates`): star score descending, ``line_ok`` failures
    below equal-scored accepted names, ticker breaking any remaining tie.

    ``entered`` is the set of tickers an executed trade was entered in on this
    session; ``any_entry`` is whether any trade was entered at all. A detection is
    a *not-taken detection* when a trade was entered this session but not in its
    name (PRD user story 25), and a *taken detection* when its own name was the one
    entered — the two groups A3's selection contrast compares (issue #122).
    """
    entered = set(entered)
    gated = detection_gate(ranks)
    scored = [
        (det, seven_dimension_score(det, prior_move=det.symbol in gated))
        for det in detections
    ]
    scored.sort(key=lambda ds: (-ds[1].stars, not ds[0].line_ok, ds[0].symbol))
    return [
        ScoredDetection(
            symbol=det.symbol,
            detection=det,
            score=score,
            star_rank=rank,
            not_taken=any_entry and det.symbol not in entered,
            taken=det.symbol in entered,
        )
        for rank, (det, score) in enumerate(scored, start=1)
    ]


def _entries_by_session(trades: Iterable[ExecutedTrade]) -> dict[date, set[str]]:
    """Map each entry session to the tickers an executed trade was entered in.

    Keyed on the entry date itself — the session a name was taken on — so a
    detection on that session in any *other* name is a not-taken detection.
    """
    out: dict[date, set[str]] = {}
    for t in trades:
        out.setdefault(t.entry_date, set()).add(t.ticker)
    return out


def replay_field(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    trades: Iterable[ExecutedTrade] = (),
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
) -> list[FieldSession]:
    """Replay the field — detections, candidates and star scores — per session.

    Runs the forward chain (:func:`replay.chain.replay_chain`) to rebuild and
    persist universe membership and ranks over the window, then for each measured
    (non-burn-in) session runs the app's :func:`screener.pipeline.rebuild_detections`
    over that session's universe — gated on the detection lookbacks' deciles,
    unmodified — persisting the detections and deriving a seven-dimension star
    score for each. The detections are the persisted field rows; the star score is
    derived from them, never stored, exactly as the app derives its list.

    ``trades`` marks the not-taken detections: a field member on a session where a
    trade was entered elsewhere (user story 25). ``blind_spot_tickers`` is stamped
    as the coverage figure onto every returned field (user story 22). Returns one
    :class:`FieldSession` per measured session, in order.
    """
    chain = replay_chain(
        store,
        market,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
        sessions=sessions,
    )
    entries = _entries_by_session(trades)

    fields: list[FieldSession] = []
    for sf in chain:
        detections = rebuild_detections(store, market, sf.session)
        entered = entries.get(sf.session, set())
        candidates = build_field(
            detections, sf.ranks, entered=entered, any_entry=bool(entered)
        )
        fields.append(
            FieldSession(
                session=sf.session,
                burn_in=False,
                members=sf.members,
                detections=candidates,
                blind_spot_count=sf.blind_spot_count,
            )
        )
    return fields
