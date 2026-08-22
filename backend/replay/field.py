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
replayed score therefore totals **eight** weighted points, not the app's own nine
(PRD #138), and is always labelled a :data:`SEVEN_DIM_LABEL` so it can never be
confused with the app's full score. The labels table is never read: a dummy
sector share is handed to :func:`screener.score.star_score`, and the one row it
decides is discarded.

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
from typing import Callable, Iterable, Mapping, Sequence

from screener.detection import DETECTION_LOOKBACKS, Detection, detection_gate
from screener.pipeline import rebuild_detections
from screener.ranks import Rank
from screener.relative_strength import rs_line_for
from screener.score import DIMENSIONS, Dimension, star_score
from screener.source import MARKET_INDEX
from screener.store import Store

from .caching_store import CachingStore
from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, SessionField, replay_chain
from .reference import ExecutedTrade

# The sector dimension, dropped from the replayed score (PRD "Star score in
# replay"). Named so :func:`seven_dimension_score` strikes exactly the app's
# sector row and nothing else.
SECTOR_DIMENSION = "Sector"

# The app's full weighted total minus the dropped sector dimension's weight,
# derived from the rubric itself so a reweight carries here instead of leaving a
# hard-coded ceiling stale (PRD #138 cut the app's total from ten points to nine,
# and this from nine to eight). The replayed score always totals out of this
# ceiling, and is always labelled a seven-dimension score so it is never confused
# with the app's own full score.
SEVEN_DIM_MAX_POINTS = sum(
    weight for name, weight in DIMENSIONS if name != SECTOR_DIMENSION
)
SEVEN_DIM_LABEL = "seven-dimension score"


@dataclass(frozen=True)
class SevenDimScore:
    """The replayed star score for one detection — seven of eight dimensions.

    ``points`` is the weighted points hit, out of :data:`SEVEN_DIM_MAX_POINTS`
    (eight, PRD #138); ``stars`` is ``points / 2``. ``breakdown`` is the seven
    surviving :class:`screener.score.Dimension` rows in the app's published order,
    the sector row absent. ``label`` is :data:`SEVEN_DIM_LABEL` on every emitted
    score, so the replayed figure is never mistaken for the app's full one.
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
    surviving seven dimensions are re-totalled out of :data:`SEVEN_DIM_MAX_POINTS`.
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

    ``rs_line`` is the **candidate dimension** (#160): whether the name held its
    ratio to the benchmark across its own base
    (:func:`screener.relative_strength.rs_line_for`). It sits beside the score
    rather than inside it, because it is *not scored* — :data:`SevenDimScore`
    stays exactly the seven dimensions the rubric weighs, so a dimension under
    measurement can never quietly move a star or a ``star_rank`` while the
    question of whether it belongs is open. A3's selection contrast reads it as
    a candidate column.

    It was measured and **not admitted** (findings §5d): a wrong-way gap, so
    criterion 4 refused it and the rubric never read it. The field still computes
    it, because that is what makes §5d reproducible rather than quotable.
    """

    symbol: str
    detection: Detection
    score: SevenDimScore
    star_rank: int
    not_taken: bool
    taken: bool = False
    rs_line: bool = False


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


def star_order_key(stars: float, det: Detection) -> tuple[float, bool, str]:
    """The field's candidate order, as one rule: stars descending, then a drawable
    line, then ticker.

    Shared rather than repeated because the order is read in two places under two
    different rubrics — :func:`build_field` ranks the live field, and the paired A2
    re-run (:mod:`replay.placement`, #136) re-ranks that same field under a
    superseded rubric to see whether a pick's board place moved. Two copies of this
    key would let the re-ranked board drift out of agreement with the live one the
    moment the live order changed, and the drift would be silent.
    """
    return (-stars, not det.line_ok, det.symbol)


def build_field(
    detections: list[Detection],
    ranks: list[Rank],
    *,
    entered: Iterable[str] = (),
    any_entry: bool = False,
    lookbacks: Sequence[str] = DETECTION_LOOKBACKS,
    rs_line_of: Mapping[str, bool] | None = None,
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

    ``lookbacks`` is the gate's lookback set, defaulting to the live
    :data:`~screener.detection.DETECTION_LOOKBACKS`. It is a parameter only so the
    gate-width sweep (:mod:`replay.gate_sweep`, #149) can score a field under the
    width that admitted it — a name admitted by a widened gate holds the prior-move
    point under that gate, and scoring it against the live gate would understate it.

    ``rs_line_of`` maps symbol → the candidate dimension (#160),
    computed by the caller because it needs a second symbol's bars. It rides on
    each :class:`ScoredDetection` and is **never scored**: a symbol absent from it
    is ``False``, and the star order is identical whether it is supplied or not.
    """
    entered = set(entered)
    rs_line_of = rs_line_of or {}
    gated = detection_gate(ranks, lookbacks=lookbacks)
    scored = [
        (det, seven_dimension_score(det, prior_move=det.symbol in gated))
        for det in detections
    ]
    scored.sort(key=lambda ds: star_order_key(ds[1].stars, ds[0]))
    return [
        ScoredDetection(
            symbol=det.symbol,
            detection=det,
            score=score,
            star_rank=rank,
            not_taken=any_entry and det.symbol not in entered,
            taken=det.symbol in entered,
            rs_line=rs_line_of.get(det.symbol, False),
        )
        for rank, (det, score) in enumerate(scored, start=1)
    ]


def session_rs_lines(
    store: Store, market: str, detections: Iterable[Detection]
) -> dict[str, bool]:
    """The candidate RS-line dimension for each of a session's detections (#160).

    ``RS = adj_close(name) / adj_close(index)``, hit when today's ratio is at or
    above the ratio at the detection's own ``base_start``; the benchmark is
    :data:`~screener.source.MARKET_INDEX` for the market. Computed here rather
    than inside the score because it needs a *second* symbol's bars, and
    :mod:`screener.score` is pure and does no I/O — the same reason ``prior_move``
    and ``sector_share`` are caller-supplied.

    Reads whole bar series (through the run-scoped cache, as every other stage
    does) and never slices to the session: :func:`screener.relative_strength.rs_line`
    reads the two named sessions *exactly*, both of which are on or before the
    detection's own, so no later bar can leak in. A benchmark with no bar on
    either session scores ``False`` and is never carried forward.
    """
    index_bars = store.bars(market, MARKET_INDEX[market])
    return {
        det.symbol: rs_line_for(det, store.bars(market, det.symbol), index_bars)
        for det in detections
    }


def _entries_by_session(trades: Iterable[ExecutedTrade]) -> dict[date, set[str]]:
    """Map each entry session to the tickers an executed trade was entered in.

    Keyed on the entry date itself — the session a name was taken on — so a
    detection on that session in any *other* name is a not-taken detection.
    """
    out: dict[date, set[str]] = {}
    for t in trades:
        out.setdefault(t.entry_date, set()).add(t.ticker)
    return out


def _session_detections(
    store: Store, market: str, sf: SessionField
) -> list[Detection]:
    """A session's detections, reused from the store if already persisted (#126).

    :func:`screener.pipeline.rebuild_detections` appends through the write-once
    guard, so a second field replay over the same store used to die on the first
    session already carrying detection rows. Here a session whose detections are
    already persisted is read back rather than recomputed, which both keeps the
    store re-runnable and reproduces the first run exactly.

    A session that produced *no* detections leaves no rows, so it is recomputed —
    ``rebuild_detections`` re-runs the detector over that night's gated members
    and appends nothing (an empty append is a write-once no-op). It reproduces the
    empty result deterministically: the rank table the decile gate reads is the
    chain's own, which :func:`replay.chain._replay_session` recomputes identically
    on every pass, so a night that detected nothing the first time detects nothing
    again.

    **The gate reads the chain's ranks, not the store's.** ``Store.append_ranks``
    prunes rows outside :data:`screener.store.RANK_RETENTION_YEARS` as the chain
    advances, and the whole chain is built before this stage runs — so every
    measured session outside the retained window would gate against an *empty*
    rank table and yield no detections at all. The chain already carries the ranks
    it computed for each session, recomputed in memory on reuse for exactly this
    reason, and the A1 funnel already reads its decile verdicts from there; handing
    the same table here puts the two analyses on one rank table instead of two.
    """
    persisted = store.detections(market, sf.session)
    if persisted:
        return persisted
    return rebuild_detections(store, market, sf.session, ranks=sf.ranks)


def build_field_sessions(
    store: Store,
    market: str,
    chain: Sequence[SessionField],
    *,
    trades: Iterable[ExecutedTrade] = (),
    progress: Callable[[int, int, date], None] | None = None,
) -> list[FieldSession]:
    """Run the per-session detection pass over an already-built forward ``chain``.

    The chain-free core of :func:`replay_field`: given the chain the caller already
    computed (universe + ranks per session), it runs the app's detector once per
    measured session and derives the seven-dimension star score, so the one-process
    runner (:mod:`replay.study`) can compute the chain and the detection pass each
    exactly once and share the field across all four analyses.

    ``progress`` is called as ``progress(i, total, session)`` after each session's
    detections are built (1-based ``i``), so a long run reports rather than hanging
    silently. The store is wrapped in the run-scoped bar cache if it is not already.
    """
    store = CachingStore.wrap(store)
    entries = _entries_by_session(trades)

    total = len(chain)
    fields: list[FieldSession] = []
    for i, sf in enumerate(chain, start=1):
        detections = _session_detections(store, market, sf)
        entered = entries.get(sf.session, set())
        candidates = build_field(
            detections, sf.ranks, entered=entered, any_entry=bool(entered),
            rs_line_of=session_rs_lines(store, market, detections),
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
        if progress is not None:
            progress(i, total, sf.session)
    return fields


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
    # Cache bar reads for the whole run (issue #125): the detection stage below
    # re-reads each member's history every session just as the chain does, so wrap
    # once here and hand the same cache to both. replay_chain's own ``wrap`` sees
    # it is already a cache and reuses it rather than nesting a cold one.
    store = CachingStore.wrap(store)

    chain = replay_chain(
        store,
        market,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
        sessions=sessions,
    )
    return build_field_sessions(store, market, chain, trades=trades)
