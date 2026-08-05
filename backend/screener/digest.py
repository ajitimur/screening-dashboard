"""The digest: tonight's breaks, one dated Markdown file per market (spec §6).

**v1 does not alert.** The whole notification layer is one dated Markdown file per
market per session — the file you may read at 10pm or ignore at no cost. This
module turns yesterday's setups into today's breaks and renders that file.

The membership rule is one sentence and carries no taxonomy:

    report a name iff  close_today > trigger_yesterday

Because ``trigger_yesterday`` is the highest high of the k bars ending yesterday,
this is literally *"today's close is above the last four sessions' high"* — a
sentence a trader checks by eye, so the file says it that way. Membership consults
**neither the score nor the stop nor ``line_ok``**: those decide the watchlist's
order, not whether a break happened.

Three properties are load-bearing and easy to get wrong:

- **Every break is reported; repeats are marked, not suppressed.** A name re-arms
  the night after it breaks and can break again, higher — continuation, not
  flapping. A repeat carries a marker and the date it was last reported; nothing
  is withheld, because withholding a second, higher break is a judgement the
  digest is structurally not for (spec §6).
- **The stop column is the breakout day's low, not the cluster low.** ``entry −
  breakout_day_low`` is §7's *actual* default stop, and the breakout day is a
  daily bar already ingested when the digest renders. So the watchlist and the
  digest deliberately show **different** stops (spec §6 row format).
- **An empty night still writes the file**, with an explicit no-breaks line — so a
  *missing* file unambiguously means the run failed. That is the whole of v1's
  run-failure alerting (spec §6).

Composed from what the pipeline published, mirroring the candidate list: yesterday's
detection rows (the trigger and the score's signal vector), yesterday's rank table
(the prior-move gate and the leave-one-out sector share) and the label cache (the
industry). The break itself is read off **today's** bar — its close and its low.
The star score is **derived**, never stored, exactly as on the list (spec §7.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .bars import Bar
from .detection import Detection, detection_gate
from .ranks import Rank
from .score import star_score
from .sectors import leave_one_out_sector_shares


@dataclass(frozen=True)
class DigestBreak:
    """One reported break: yesterday's setup that today's close cleared.

    ``stopw_adr`` is computed from the **breakout day's low** (``(trigger −
    breakout_day_low) / trigger / adr``), §7's real default stop and deliberately
    different from the watchlist's cluster-low stop. ``pct_through`` is how
    decisive the break was, ``(close − trigger) / trigger`` in percent.
    ``line_ok`` never appears here — the fit's quality is a silent tiebreak on the
    order, not a field on the row (spec §6).
    """

    symbol: str
    score: float
    industry: str | None
    stopw_adr: float          # from the breakout day's low, not the cluster low
    close: float              # today's close — the level the rule tests
    trigger: float            # yesterday's trigger — the level tested against
    pct_through: float        # (close − trigger) / trigger, percent
    repeat: bool
    last_reported: date | None


def build_digest(
    yesterday_detections: list[Detection],
    today_bars: dict[str, Bar],
    ranks_yesterday: list[Rank],
    industry_of: dict[str, str],
    sector_of: dict[str, str],
    last_reported: dict[str, date],
) -> list[DigestBreak]:
    """Tonight's breaks, **ordered by star score descending** (spec §6).

    ``yesterday_detections`` are the setups that carry a ``trigger_yesterday``;
    ``today_bars`` maps symbol → today's bar (its close is the level tested, its
    low the breakout-day stop). ``ranks_yesterday`` is yesterday's rank table, read
    for the score's prior-move gate and leave-one-out sector share — the score of
    the setup that broke, computed exactly as the list computed it. ``last_reported``
    maps symbol → the most recent prior session it was reported, for the repeat
    marker; a symbol absent from it is a first-time break.

    A name is reported **iff** its today close exceeds its yesterday trigger — the
    score, the stop and ``line_ok`` are computed for the row but never gate
    membership. A name with no bar today cannot be tested and is silently absent.
    """
    prior_move = detection_gate(ranks_yesterday)
    sector_shares = leave_one_out_sector_shares(ranks_yesterday, sector_of)

    rows = []
    for det in yesterday_detections:
        bar = today_bars.get(det.symbol)
        if bar is None or bar.close <= det.trigger:
            continue  # no bar to test, or the close did not clear the trigger
        stars, _breakdown = star_score(
            det,
            prior_move=det.symbol in prior_move,
            sector_share=sector_shares.get(det.symbol, 0.0),
        )
        # §7's real default stop: entry − breakout_day_low, normalised to one ADR
        # the same way the detection normalises its cluster-low stop.
        stopw_adr = (
            (det.trigger - bar.low) / det.trigger / det.adr
            if det.trigger > 0 and det.adr > 0
            else float("nan")
        )
        rows.append(
            (
                det,
                DigestBreak(
                    symbol=det.symbol,
                    score=stars,
                    industry=industry_of.get(det.symbol),
                    stopw_adr=stopw_adr,
                    close=bar.close,
                    trigger=det.trigger,
                    pct_through=(bar.close - det.trigger) / det.trigger * 100.0,
                    repeat=det.symbol in last_reported,
                    last_reported=last_reported.get(det.symbol),
                ),
            )
        )
    # Star score descending; line_ok failures a silent tiebreak below equal-scored
    # accepted names; ticker breaks any final tie — matching the list (spec §4.7/§6).
    rows.sort(key=lambda r: (-r[1].score, not r[0].line_ok, r[0].symbol))
    return [b for _det, b in rows]


def _stars(score: float) -> str:
    """``3.0`` → ``3★``, ``3.5`` → ``3.5★`` — the compact star glyph the list uses."""
    return f"{score:g}★"


def render_digest(market: str, session: date, breaks: list[DigestBreak]) -> str:
    """The dated Markdown file's text (spec §6).

    A header naming the market and session, the membership rule stated the way a
    trader checks it by eye, and one row per break ordered by star score. An empty
    ``breaks`` still renders — with an explicit no-breaks line — so a *missing*
    file is the failed-run signal and an empty one is a quiet night.
    """
    lines = [
        f"# {market} digest — {session.isoformat()}",
        "",
        "Report a name when today's close is above yesterday's trigger — "
        "i.e. today's close is above the last four sessions' high.",
        "",
    ]
    if not breaks:
        lines.append("No breaks tonight.")
        return "\n".join(lines) + "\n"

    lines += [
        "| Ticker | Score | Industry | Stop ÷ADR | Close | Trigger | % through | |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b in breaks:
        marker = (
            f"↺ last reported {b.last_reported.isoformat()}"
            if b.repeat and b.last_reported is not None
            else ""
        )
        lines.append(
            f"| {b.symbol} | {_stars(b.score)} | {b.industry or '—'} "
            f"| {b.stopw_adr:.2f} | {b.close:.2f} | {b.trigger:.2f} "
            f"| {b.pct_through:+.2f}% | {marker} |"
        )
    return "\n".join(lines) + "\n"
