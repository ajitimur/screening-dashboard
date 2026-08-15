"""A2 reporting: where each executed trade sat in that night's replayed field
(PRD #114 "A2 replay chain", issue #120).

The field itself — universe, ranks, detections, candidates and the
seven-dimension star score — is built by :mod:`replay.field` (#118). This lands
the *reporting* on top of it: for every executed trade, where it sat within the
replayed field on the last session strictly before its entry.

**Deliberately only two statements per trade.** Whether the trade appeared in the
field at all, and whether it landed inside the top thirty by star score — the
board size the trader actually reads (:data:`BOARD_SIZE`, the app's own
:data:`screener.boards.BOARD_SIZE`, never a separately chosen constant). And per
session, the star distribution of his picks against the star distribution of the
field.

**No percentile, no rank position.** The field is missing roughly a quarter of
its names, and those missing names are disproportionately the ones that later
died — precisely the population a momentum screener surfaces. A percentile over
that field would look precise while quietly flattering the rubric. A top-thirty
hit and a star distribution are coarser statements that survive the missing
field, so a :class:`TradePlacement` carries the two booleans and the star score,
never a rank index or percentile (PRD "Further Notes"; acceptance: "No percentile
or rank-position figure is emitted anywhere").

**The star distribution is the prize.** If his picks cluster at the top of the
rubric it discriminates; if they spread flat across the range it does not, and
that is the single most valuable thing this study can return (issue #120).

**Coverage and scope.** Every output carries its coverage number against the
committed blind-spot tickers (user story 22), and the whole study is scoped to
:data:`SCOPE` — US 2019–2022 — and is not presented as an IDX expectation (user
story 35). A blind-spot trade (ticker with no bars) is *not* placed: it is a
blind spot counted in coverage, never an absent-from-field verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

from screener.boards import BOARD_SIZE
from screener.store import Store

from .chain import BURN_IN_SESSIONS, REPLAY_MARKET
from .field import FieldSession, replay_field
from .funnel import evaluation_session
from .reference import ExecutedTrade, classify

# The study is scoped to US 2019–2022 and no figure from it is to be presented as
# an IDX expectation (PRD user story 35 / Out of Scope). Stamped on every output.
SCOPE = "US 2019–2022"


@dataclass(frozen=True)
class TradePlacement:
    """Where one executed trade sat in that night's replayed field.

    Keyed to ``eval_session`` — the last market session strictly before entry,
    the night the app would have had to name the stock. Deliberately only two
    statements: ``in_field`` (it appeared at all) and ``top_thirty`` (it landed
    inside the board the trader reads). ``stars`` is its seven-dimension star
    score when in the field, else ``None``. No rank position or percentile is
    carried — those would flatter a field missing a quarter of its names.
    """

    ticker: str
    entry_date: date
    eval_session: date | None
    in_field: bool
    top_thirty: bool
    stars: float | None


@dataclass(frozen=True)
class StarDistribution:
    """A histogram of star scores — the shape of a set of picks, not a percentile.

    ``counts`` maps each star value (a multiple of 0.5, 0 to 4.5) to how many
    scores landed on it; ``total`` is the number of scores. Comparing his picks'
    distribution against the field's on the same sessions is the study's prize
    (issue #120): a cluster at the top says the rubric discriminates, a flat
    spread says it does not.
    """

    counts: Mapping[float, int]
    total: int

    @classmethod
    def from_stars(cls, stars: Iterable[float]) -> "StarDistribution":
        counts: dict[float, int] = {}
        total = 0
        for s in stars:
            counts[s] = counts.get(s, 0) + 1
            total += 1
        return cls(counts=counts, total=total)


@dataclass(frozen=True)
class PlacementReport:
    """The A2 result: per-trade placements plus the two star distributions.

    ``picks`` is the star distribution of his executed trades that appeared in the
    field; ``field`` is the star distribution of the whole field on the same
    sessions his trades were evaluated against. ``board_size`` is the app's own
    board size (the top-N cut). ``blind_spot_count`` is the coverage figure every
    field-derived output must carry (user story 22); ``scope`` is :data:`SCOPE`.
    """

    placements: list[TradePlacement]
    picks: StarDistribution
    field: StarDistribution
    board_size: int
    blind_spot_count: int
    scope: str = SCOPE

    @property
    def in_field_count(self) -> int:
        """How many placed trades appeared in the field at all."""
        return sum(1 for p in self.placements if p.in_field)

    @property
    def top_thirty_count(self) -> int:
        """How many placed trades landed inside the board the trader reads."""
        return sum(1 for p in self.placements if p.top_thirty)


def place_trade(
    trade: ExecutedTrade, eval_session: date | None, field: FieldSession | None
) -> TradePlacement:
    """Place one executed trade within its evaluation session's field.

    ``field`` is the replayed field for the last session strictly before entry, or
    ``None`` when no measured session precedes it (nothing to place against). The
    top-thirty flag is the candidate's star rank against :data:`BOARD_SIZE`, the
    app's board size — the list the trader actually reads. A trade absent from the
    field is distinguished from one present but outside the top thirty: only the
    present one is ``in_field``.
    """
    match = None
    if field is not None:
        match = next(
            (det for det in field.detections if det.symbol == trade.ticker), None
        )
    return TradePlacement(
        ticker=trade.ticker,
        entry_date=trade.entry_date,
        eval_session=eval_session,
        in_field=match is not None,
        top_thirty=match is not None and match.star_rank <= BOARD_SIZE,
        stars=match.score.stars if match is not None else None,
    )


def run_placement(
    trades: list[ExecutedTrade],
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
) -> PlacementReport:
    """Place every replayable trade in its night's field, and report the two
    star distributions.

    Runs the replayed field (:func:`replay.field.replay_field`) over the window,
    then for each replayable trade looks up the field for the session strictly
    before its entry and places it. Blind-spot trades (ticker with no bars) get no
    placement row — they are a blind spot counted in coverage, not an
    absent-from-field verdict. The picks distribution is the star scores of his
    in-field trades; the field distribution is the whole field on the same
    sessions his trades were evaluated against.
    """
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]

    fields = replay_field(
        store,
        market,
        trades=replayable,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
    )
    by_session: dict[date, FieldSession] = {f.session: f for f in fields}
    calendar = store.sessions(market)

    placements: list[TradePlacement] = []
    pick_sessions: set[date] = set()
    for trade in replayable:
        eval_session = evaluation_session(calendar, trade.entry_date)
        session_field = by_session.get(eval_session) if eval_session else None
        placement = place_trade(trade, eval_session, session_field)
        placements.append(placement)
        if session_field is not None:
            pick_sessions.add(session_field.session)

    picks = StarDistribution.from_stars(
        p.stars for p in placements if p.in_field and p.stars is not None
    )
    field_dist = StarDistribution.from_stars(
        det.score.stars
        for session in pick_sessions
        for det in by_session[session].detections
    )

    blind_spot_count = len(set(blind_spot_tickers))
    return PlacementReport(
        placements=placements,
        picks=picks,
        field=field_dist,
        board_size=BOARD_SIZE,
        blind_spot_count=blind_spot_count,
        scope=SCOPE,
    )


def format_report(report: PlacementReport) -> str:
    """Human-readable summary: the two coarse statements and the two distributions.

    States the scope (US 2019–2022, not an IDX expectation) and the coverage
    against the blind-spot tickers on every output (user stories 22, 35).
    """
    placed = len(report.placements)
    lines = [
        f"scope: {report.scope} (not an IDX expectation)",
        f"blind-spot coverage: {report.blind_spot_count} tickers missing from the field",
        "",
        f"placed trades:       {placed}",
        f"appeared in field:   {report.in_field_count}/{placed}",
        f"inside top {report.board_size}:      {report.top_thirty_count}/{placed}",
        "",
        "star distribution (his picks vs the field, same sessions):",
    ]
    all_stars = sorted(
        set(report.picks.counts) | set(report.field.counts), reverse=True
    )
    for star in all_stars:
        lines.append(
            f"  {star:>4} stars:  picks {report.picks.counts.get(star, 0):>4}  "
            f"field {report.field.counts.get(star, 0):>5}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the A2 placement over the replay store and print the report.

    Thin CLI over the pure functions above (one entry point per study, PRD user
    story 30). The blind-spot tickers are recomputed from the reference set rather
    than passed in, so the coverage figure on the report is always the store's own.
    Run as ``python -m replay.placement --store data/replay.duckdb``.
    """
    import argparse

    from .reference import DEFAULT_REFERENCE_JSON, build_report, load_trades

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        coverage = build_report(trades, store, market=args.market)
        report = run_placement(
            trades,
            store,
            args.market,
            blind_spot_tickers=coverage.blind_spot_ticker_list,
        )
    finally:
        store.close()

    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
