"""The RS line: an index-relative candidate dimension, **under measurement**
(issue #160).

``RS = adj_close(name) / adj_close(index)``, hit when ``RS_today >=
RS_at_base_start``. It is a candidate for the rubric slot ``Prior move`` cannot
earn — that dimension measures pooled spread 0.000 in findings §5b, 100.0% in
both the taken and the not-taken group, so it occupies a point of a nine-point
rubric and cannot move the sort under any field (a **constant dimension**).

**Nothing here is scored.** The dimension is computed and carried so #160's
pre-registered study can measure it against the four ship criteria fixed before
the numbers were visible; :mod:`screener.score` is untouched and
:data:`screener.score.RUBRIC_VERSION` does not move. Admission is governed by
``docs/adr/0005-what-admits-a-dimension-to-the-rubric.md``.

Four properties are load-bearing, and each rules out a variant that looks
equivalent:

- **Non-decayed, not a new high.** A name that merely *matched* the index across
  its base passes. This is the whole of the rule and it has no free parameter. A
  strict-new-high form would fire only when the index fell during the base, which
  makes it a regime indicator wearing a rubric dimension's clothes — and regime
  never scores (spec §4.9).
- **The window is the detection's own base**, anchored at the detector's actual
  ``base_start`` — which re-anchors to the highest high within
  :data:`~screener.detection.MAX_BASE_LEN` bars when the base is capped, and is
  therefore *not* the prior-move peak on a capped base.
- **Both legs read ``adj_close``.** A ratio on unadjusted closes jumps on every
  split.
- **A missing bar scores ``False``, never carried forward.** Phantom bars are
  removed from a series entirely and never zero-filled (§2 *Phantom bar*);
  inventing an index price to score against would break the same rule. Scoring
  ``False`` costs at most one point on a rare edge, where *excluding* the name
  would let a data gap remove a candidate from the list. This is the one place
  the module deliberately departs from :func:`screener.indicators.calendar_return`,
  which reads the last bar on or before its anchor.

**Computed in the caller, never in :mod:`screener.score`.** The score module is
pure and does no I/O, and that guarantee is worth keeping; the RS line needs a
second symbol's bars, so it joins ``prior_move`` and ``sector_share`` as a
caller-supplied cross-sectional input. The benchmark is
:data:`~screener.source.MARKET_INDEX` as it stands — ``^IXIC`` (US), ``^JKSE``
(IDX).

**No schema change.** :class:`~screener.detection.Detection` persists ``base_len``
and ``session``, and the bars table has no retention cap, so ``base_start`` — and
with it the whole dimension — is recomputable from stored bars for any past
session. The replay property in spec §7.5 survives intact.

Pure over two clean, oldest-first ``list[Bar]`` series, so it is unit-tested
without the network.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from .bars import Bar
from .detection import Detection


def _adj_close_on(bars: list[Bar], when: date) -> float | None:
    """The adjusted close of the bar dated **exactly** ``when``; ``None`` if the
    series has no bar that session.

    Exact, not "last bar on or before" — that is the missing-bar rule stated in
    the module docstring, and the reason this is not
    :func:`screener.indicators._last_adj_close_on_or_before`. A benchmark that did
    not print a bar is *absent*, and carrying the previous session's price forward
    would score the name against a price the index never had.
    """
    sessions = [b.session for b in bars]
    idx = bisect_right(sessions, when) - 1
    if idx < 0 or sessions[idx] != when:
        return None
    return bars[idx].adj_close


def rs_line(
    bars: list[Bar], index_bars: list[Bar], *, base_start: date, as_of: date
) -> bool:
    """Whether the name held its ratio to the benchmark across its base.

    ``bars`` is the name's series and ``index_bars`` the benchmark's, both clean
    and oldest-first; ``base_start`` and ``as_of`` are the base's first and last
    sessions. True when ``adj_close(name)/adj_close(index)`` at ``as_of`` is at or
    above the same ratio at ``base_start`` — *at or above*, so matching the index
    is a hit (see the module docstring on why a new-high form is rejected).

    ``False`` whenever any of the four prices is missing or non-positive: the
    dimension is never carried forward and never excludes the name.
    """
    prices = (
        _adj_close_on(bars, base_start),
        _adj_close_on(index_bars, base_start),
        _adj_close_on(bars, as_of),
        _adj_close_on(index_bars, as_of),
    )
    if any(p is None or p <= 0 for p in prices):
        return False
    name_start, index_start, name_now, index_now = prices  # type: ignore[misc]
    return name_now / index_now >= name_start / index_start


def base_start_session(
    bars: list[Bar], session: date, *, base_len: int
) -> date | None:
    """The session the base began, ``base_len`` **traded bars** back from
    ``session`` inclusive; ``None`` if the series does not reach that far back.

    This is what makes the dimension replayable with no schema change: the
    detector does not persist ``base_start``, but it persists ``base_len``, and
    the base always ends at the detection's own session (§2 *Base*: "Always ends
    today — there is no such thing as a base that ended last week"). Counting
    *traded* bars is the detector's own convention — its base runs over series
    indices, so weekends, holidays and phantom-dropped bars are simply absent.

    ``session`` is resolved to the last bar on or before it, so a caller handing
    in a session the name did not trade is anchored on the bar the detector would
    have used rather than silently shifting the base forward.
    """
    sessions = [b.session for b in bars]
    end = bisect_right(sessions, session) - 1
    start = end - base_len + 1
    if end < 0 or start < 0:
        return None
    return sessions[start]


def rs_line_for(det: Detection, bars: list[Bar], index_bars: list[Bar]) -> bool:
    """The RS line for one detection, over its own base.

    Resolves ``base_start`` off the detection's ``base_len`` and ``session``
    (:func:`base_start_session`) and applies :func:`rs_line`. ``False`` when the
    base reaches back past the start of the stored series — the same
    never-carried-forward rule as a missing bar.
    """
    base_start = base_start_session(bars, det.session, base_len=det.base_len)
    if base_start is None:
        return False
    return rs_line(bars, index_bars, base_start=base_start, as_of=det.session)
