"""Index-relative **candidate dimensions** — quantities under measurement for the
rubric slot ``Prior move`` cannot earn, and scored by nothing here.

Two live in this module, in the order they were registered under
``docs/adr/0005-what-admits-a-dimension-to-the-rubric.md``:

- **RS line** (#160) — the ratio to the index across the detection's own base.
  Measured and **rejected** (findings §5d).
- **Relative move** (#170) — the `6m` return relative to the index, compounded,
  in ADR units. **Pre-registered, not yet measured**; #171 runs the contrast.

They share a benchmark and a never-carried-forward rule and differ in the one
thing §5d's post-mortem named as the mechanism behind its null: the **anchor**.
The RS line measures from ``base_start``, a local high, over a median 12-session
window; the relative move measures from a fixed calendar date that on the modal
detection sits about five months before the base begins. That is what makes the
second a different statistic rather than the first re-registered, and ADR 0005
records what result would say the distinction did not matter.

**Computed in a caller, never in :mod:`screener.score`.** The score module is
pure and does no I/O, and that guarantee is worth keeping; both dimensions need a
*second symbol's* bars, so either could only ever be a caller-supplied
cross-sectional input like ``prior_move`` and ``sector_share``. The benchmark is
:data:`~screener.source.MARKET_INDEX` as it stands — ``^IXIC`` (US), ``^JKSE``
(IDX).

Pure over clean, oldest-first ``list[Bar]`` series, so both are unit-tested
without the network.

## The RS line, and why it was refused

``RS = adj_close(name) / adj_close(index)``, hit when ``RS_today >=
RS_at_base_start``. It was proposed for the rubric slot ``Prior move`` cannot
earn — that dimension measures pooled spread 0.000 in findings §5b, 100.0% in
both the taken and the not-taken group, so it occupies a point of a nine-point
rubric and cannot move the sort under any field (a **constant dimension**).

**The verdict was do not ship**, on criterion 4 of the four pre-registered in
``docs/adr/0005-what-admits-a-dimension-to-the-rubric.md``: the gap is *negative*
on both measured fields — −5.8pp under detector v1, −2.1pp under the live
detector — so he selects names whose strength against the index decayed through
the base. Criterion 2 would have refused it regardless, at 11.2% disagreement
with price-at-a-new-high-over-base against a pre-registered ~15% floor.

**So nothing here is scored, and nothing in the app calls it.** :mod:`screener.score`
is untouched, :data:`screener.score.RUBRIC_VERSION` stays 3, and the live
candidate list, digest and chart never compute it — the wiring that would have
carried it to the scorer came out with the verdict, as it said it would. The
module survives because the *evidence* has to stay reproducible: it is what
:func:`replay.field.session_rs_lines` and ``scripts/rs_line_contrast.py`` read,
and re-running the study is how anyone checks §5d rather than trusting it.

Read it as the worked example of a candidate dimension, not as live scoring code.

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
  therefore *not* the prior-move peak on a capped base. Either way it is a
  **local high**, which is what makes the dimension hard to hit and is the
  mechanism behind its null (findings §5d). Capped bases are 1.9% of the
  measured field, so the two branches are not equally common — but the property
  that matters holds under both.
- **Both legs read ``adj_close``.** A ratio on unadjusted closes jumps on every
  split.
- **A missing bar scores ``False``, never carried forward.** Phantom bars are
  removed from a series entirely and never zero-filled (§2 *Phantom bar*);
  inventing an index price to score against would break the same rule. Scoring
  ``False`` costs at most one point on a rare edge, where *excluding* the name
  would let a data gap remove a candidate from the list. This is the one place
  the module deliberately departs from :func:`screener.indicators.calendar_return`,
  which reads the last bar on or before its anchor.

**No schema change.** :class:`~screener.detection.Detection` persists ``base_len``
and ``session``, and the bars table has no retention cap, so ``base_start`` — and
with it the whole dimension — is recomputable from stored bars for any past
session. The replay property in spec §7.5 survives intact.

## The relative move, and what is fixed about it in advance

The registration is ADR 0005's; what lives here is the executable half of it, so
that "the exact definition" is a thing #171 imports rather than a paragraph it
re-reads. Three choices are load-bearing and each rules out a variant that looks
equivalent:

- **`6m`, chosen before the contrast exists** (:data:`RELATIVE_MOVE_LOOKBACK`).
- **Compounded, not subtracted** — see :func:`relative_move_adr`.
- **The cut sits at zero** (:data:`RELATIVE_MOVE_CUT`), which is also why the
  boolean is ADR-invariant: the units buy the stored *value*, not the pass/fail.

What the units are for is the part worth reading twice. ADR 0005 admits a
dimension as a **boolean** — grading needs demonstrated signal, and a candidate
has none by definition — so nothing here grades anything. But a breakdown row
carries the *value* and the rubric owns the mapping (#154), and a row cannot be
re-denominated retroactively. Persisting the relative move in ADR units now is
what would let ADR 0004's grading question be asked later, on measured evidence,
without re-scoring history.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from .bars import Bar
from .detection import Detection
from .indicators import adr, calendar_return


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


# The window the `Relative move` candidate is registered over (#170). Six months,
# fixed in advance on two figures §3f published before the registration: the
# beat-rate against the index is *higher* at `6m` (74.2%) than at `12m` (67.5%),
# and the `12m` ADR-unit gap, though larger, is the noisier column — §3f records
# it as set by a handful of ten-baggers against an ordinary day's +0.4% median.
# One window, no sweep: trying `3m`/`6m`/`12m` and keeping the widest gap is the
# magnitude-fitting ADR 0005's pre-registration clause exists to prevent.
RELATIVE_MOVE_LOOKBACK = "6m"

# The pre-registered cut-point, in ADR units. **Zero, and it has to be.** ADR is
# positive, so the denominator cannot flip a sign — the boolean is ADR-invariant
# and "outran the index" is the whole rule, with no free parameter. Any non-zero
# cut would be a magnitude read off the replay, which #128 Q2 forbids, and no
# published bucket boundary supports one here: §3f denominates the *raw* returns
# in ADR, not the relative ones, so even ADR 0004's "use the study's own bucket
# edges" route is unavailable.
RELATIVE_MOVE_CUT = 0.0


def relative_move_adr(
    bars: list[Bar],
    index_bars: list[Bar],
    as_of: date,
    *,
    lookback: str = RELATIVE_MOVE_LOOKBACK,
) -> float | None:
    """The name's ``lookback`` return relative to the benchmark, in ADR units.

    ``(1 + r(name)) / (1 + r(index)) − 1``, divided by the name's own
    :func:`~screener.indicators.adr`. Compounded rather than subtracted because
    over these horizons a percentage-point difference and a multiple are
    different quantities, and only the second means "outran the market"
    (findings §3f).

    Both legs are :func:`~screener.indicators.calendar_return` — the rank table's
    own definition, calendar-anchored, resolving to the last bar **on or before**
    the anchor. That is the one place this departs from :func:`rs_line`, and
    deliberately: an anchor six calendar months back lands on a weekend or a
    holiday about three days in ten, so an exact-bar rule would score a calendar
    artefact rather than the name. The RS line's anchors are traded sessions by
    construction, which is why exactness was free there.

    **The ADR leg is sliced to ``as_of`` before it is taken.**
    :func:`~screener.indicators.adr` averages the last 20 bars of whatever series
    it is handed, and :mod:`replay.field` hands whole series in and never slices
    them to the session — a convention that is safe for :func:`rs_line` only
    because that function reads two named sessions exactly. Without the slice a
    2019 session would be denominated by 2022's volatility, and the study would
    never see it: the leak is invisible in any fixture whose range is constant.

    ``None`` — **absent, not zero** — when either leg has no bar on or before its
    anchor (the name had not listed, the benchmark's series does not reach back)
    or the name has fewer than 20 bars through ``as_of`` for an ADR. Callers score
    that ``False`` via :func:`relative_move_hit`; the value is never carried
    forward and never excludes the name.
    """
    name_return = calendar_return(bars, as_of, lookback)
    index_return = calendar_return(index_bars, as_of, lookback)
    if name_return is None or index_return is None or index_return <= -1:
        return None
    name_adr = adr(bars[: bisect_right([b.session for b in bars], as_of)])
    if name_adr is None or name_adr <= 0:
        return None
    return ((1 + name_return) / (1 + index_return) - 1) / name_adr


def relative_move_hit(value: float | None) -> bool:
    """The pre-registered boolean over :func:`relative_move_adr`'s value.

    Strictly above :data:`RELATIVE_MOVE_CUT`. A tie is measure-zero and the
    strictness is fixed only so the definition has no ambiguity — unlike
    :func:`rs_line`, where ``>=`` is load-bearing because *non-decayed* is the
    concept there. An absent value scores ``False``.

    One site owns the cut, so the boolean the contrast reads and the value the
    breakdown row would carry can never disagree about where the line is.
    """
    return value is not None and value > RELATIVE_MOVE_CUT
