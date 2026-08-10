"""The source client: the one module that touches the network (spec §3.1).

It does two things and only two things reach the network through it:

- **enumerate** a market's symbols, deriving each instrument's ``role``
  (candidate vs reference) at enumeration — US from the Nasdaq listing files'
  ETF flag, IDX from the Yahoo screener, each market's index folded in as a
  reference; and
- **resolve** a symbol to its bars, paced and backed off, returning a *result
  type* — never a bare list.

The symbol a caller passes is always the enumeration's own — the Nasdaq form for
US, which every stored row is keyed by. Where the provider spells it differently
(a share class is ``BRK.B`` in the listing file and ``BRK-B`` on the wire, #105)
the translation happens at the request itself, in :func:`provider_symbol`, and
is invisible above this module.

The load-bearing behaviour is a failure mode, not a feature. **Yahoo fails as
silence** (spec §3.2): a throttled request returns an empty result that is
byte-identical to a genuinely dead name. No per-symbol care can separate the two
(spec §3.4 rule 5), so the only robust move is to make the ambiguous signal
non-actionable: an empty result is ``unresolved`` and is retried with backoff —
it is *never* reported as ``absent``. Absence requires positive evidence (real
bars failing the density gate, spec §3.4 rule 6), which lives above this module.

The one break in that symmetry is a refusal Yahoo *states*: for some listings it
names the periods it will serve instead of answering with an empty frame. That
is an answer, not silence, so it resolves ``refused`` on the first attempt —
retrying a sentence only gets the sentence back.

Everything above this boundary sees a :class:`Resolution`, never an empty list,
and every test fakes *this* boundary — nothing else needs the network.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import date
from dataclasses import dataclass, field
from itertools import islice
from typing import Callable, Iterable, Iterator, Literal, Protocol, Sequence

from pydantic import BaseModel

# Pacing: 12 requests/second with exponential backoff on 429. Measured
# (spec §3.3): unthrottled returns only 52.9% of the US universe while blaming
# the losses on delisting; 12 req/s gives 99.93% coverage with zero 429s.
DEFAULT_RATE_PER_SEC = 12
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE = 1.0

# How many resolves may be in flight at once (issue #96). The rate cap above is
# a *ceiling*, and a sequential loop never reaches it: one request at a time
# bounded by Yahoo's round-trip latency spends a small fraction of the budget,
# which is why a ~7,300-name US pull took the better part of an hour rather than
# the ~10 minutes 12 req/s buys.
#
# Measured against the live provider, 30 US symbols, full history: sequential
# managed 2.7 sym/s (22% of the budget), 12 workers 10.7 sym/s (89%), and 20
# workers 10.5 sym/s — no better, because by then the workers are queueing on
# :class:`Pacer` rather than on Yahoo. So the right worker count is the rate cap
# itself: it is what fills the pacer's slots at realistic latency, and nothing
# past it buys anything. Every run resolved every symbol with zero 429s. This
# spends the pacing budget; it does not raise it.
DEFAULT_RESOLVE_WORKERS = DEFAULT_RATE_PER_SEC

# The tail sweep (issue #104): how long to rest before re-asking a pull's silent
# symbols, once per entry, and how many resolves to run while doing it.
#
# A US pull resolved 5,161 of 5,500 and put 310 of the 339 silences in its last
# 500 symbols — one contiguous alphabetical block, at the far end of an ~8-minute
# fetch, every name of which returned a full ten-year history when asked again a
# few minutes later. So the cap above is not what those requests hit: 12 req/s
# was measured over 30 symbols, and what bites after thousands of them in one
# session is a *sustained* ceiling — a per-session or per-hour allowance that no
# per-second pacing can spend its way around.
#
# Per-symbol backoff cannot wait that out either. Four attempts spread over seven
# seconds are all inside the same exhausted window, so the retry budget is spent
# before the allowance has refilled. The only thing the evidence says works is
# rest, which is what this is: two of them, escalating, each followed by a pass
# over whatever is still silent. The rate cap is untouched — the sweep runs at a
# quarter of the pull's workers, which is a lower sustained rate at the same
# ceiling, because a pass that re-throttles is a pass that answered nothing.
#
# The cost is bounded and paid only when it is needed: a clean pull rests not at
# all, and the second rest fires only if the first one left something silent. A
# nightly run can afford six minutes; a market that never publishes cannot.
SWEEP_PAUSES = (60.0, 300.0)
SWEEP_WORKERS = max(1, DEFAULT_RESOLVE_WORKERS // 4)

# One index per market, ingested like anything else but never rankable — its
# role is ``reference`` (spec §2, §4.9).
MARKET_INDEX = {"US": "^IXIC", "IDX": "^JKSE"}

# Yahoo's screener serves the exchange one fixed-size page at a time, at most
# this many quotes per call (issue #110). A single un-paged request returned only
# the first page and silently truncated IDX to 250 names against the ~840 the
# screener actually carries — so the enumeration pages by offset until the end.
IDX_SCREEN_PAGE = 250

# The Nasdaq Trader listing files (spec §3.1): common stocks plus the ETF flag
# that separates funds. Served over HTTPS, pipe-delimited, with a trailing
# "File Creation Time" footer line.
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

Role = Literal["candidate", "reference"]
ResolutionStatus = Literal["resolved", "unresolved", "refused"]


class RateLimitedError(RuntimeError):
    """A request was throttled (HTTP 429). The caller backs off and retries."""


class PermanentlyUnavailableError(RuntimeError):
    """The provider *stated* it will not serve this listing's history.

    The one case that is not silence. Yahoo answers a request for full history
    on some listings — warrants and units, typically, with barely any trading
    life — by naming the periods it will serve instead of returning an empty
    frame. That is positive evidence, not the ambiguous emptiness §3.2 is about,
    so it is the one fetch outcome a retry cannot improve: backing off and
    asking again gets the same sentence back every time.
    """


class Instrument(BaseModel):
    """Anything enumerated. ``role`` is derived at enumeration (spec §2).

    A ``reference`` instrument (a market index, or a US ETF) is ingested and
    computed like anything else but is never rankable; a ``candidate`` is a
    common stock eligible for the universe.
    """

    market: str
    symbol: str
    role: Role
    # The security name, carried for the universe's instrument-type rule (spec
    # §4.1 / ticket 05 D13). US comes from the Nasdaq listing files' "Security
    # Name" column; IDX carries none (the screener guarantees common equity).
    name: str = ""


@dataclass(frozen=True)
class Resolution:
    """The result of resolving one symbol — a type, never a bare list.

    ``resolved`` carries the fetched bars; ``unresolved`` is silence that
    survived every retry, and it is *not* ``absent`` (spec §3.4 rule 5).
    ``refused`` is the provider saying outright that it will not serve this
    listing's history — the one outcome that is evidence rather than silence,
    so it is neither retried nor counted against the completeness gate.
    """

    symbol: str
    status: ResolutionStatus
    bars: list = field(default_factory=list)
    # Whether the silence was one the provider *stated* — a 429 — rather than an
    # empty answer (issue #104). It changes nothing about the policy: both are
    # silence, both are retried, both are unresolved-not-absent. It is carried
    # because the two point at different remedies, and a quarantine that cannot
    # say which one it hit can only be diagnosed by re-running the pull by hand.
    throttled: bool = False


@dataclass(frozen=True)
class LabelResolution:
    """The result of fetching one symbol's sector/industry — a result type, the
    same shape as :class:`Resolution` for the same reason (Yahoo fails as
    silence, spec §3.2).

    ``resolved`` carries *both* labels — they arrive in one ``.info`` request
    (spec §3.1), and a name missing either cannot be placed on the axis, so a
    partial result is ``unresolved``. ``unresolved`` leaves the cached value
    intact and is retried (spec §3.3).
    """

    symbol: str
    status: ResolutionStatus
    sector: str = ""
    industry: str = ""


class SourceClient(Protocol):
    """The raw network boundary. The real implementation is the only code that
    talks to Yahoo / Nasdaq; tests supply a fake with these methods."""

    def enumerate(self, market: str) -> list[Instrument]: ...

    def fetch(self, symbol: str, start: date | None = None) -> list:
        """Return the symbol's bars, or an empty list for silence. Raises
        :class:`RateLimitedError` on a 429.

        ``symbol`` is always the enumeration's own form; translating it to
        whatever the provider answers to (:func:`provider_symbol`) is the
        client's business, not the caller's.

        ``start`` selects the request window (spec §3.6): ``None`` is a cold
        start asking for full history (``period="max"``); a date fetches from
        that session forward. The distinction is load-bearing — a *stated*
        refusal only fires on the unbounded request, so it is detectable only on
        the cold start (issue #100)."""

    def fetch_info(self, symbol: str) -> dict:
        """Return the symbol's ``.info``-style dict (``sector`` and ``industry``
        in one request), or an empty dict for silence. Raises
        :class:`RateLimitedError` on a 429."""


# -- enumeration parsing (pure, so it is unit-tested without the network) -----


def parse_us_listings(nasdaqlisted: str, otherlisted: str) -> list[Instrument]:
    """Build US instruments from the two Nasdaq Trader files.

    Role is the ETF flag: ``Y`` -> reference, else candidate. Test issues are
    dropped. The market index ``^IXIC`` is folded in as a reference.
    """
    instruments = [Instrument(market="US", symbol=MARKET_INDEX["US"], role="reference")]
    for text in (nasdaqlisted, otherlisted):
        instruments.extend(_parse_nasdaq_file(text))
    return instruments


def _parse_nasdaq_file(text: str) -> list[Instrument]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = lines[0].split("|")

    def col(*names: str) -> int:
        for name in names:
            if name in header:
                return header.index(name)
        raise ValueError(f"none of {names} in header {header}")

    sym_i = col("Symbol", "ACT Symbol")
    etf_i = col("ETF")
    test_i = col("Test Issue")
    name_i = col("Security Name")

    out: list[Instrument] = []
    for line in lines[1:]:
        fields = line.split("|")
        if fields[0].startswith("File Creation Time"):
            continue
        if len(fields) <= max(sym_i, etf_i, test_i, name_i):
            continue
        if fields[test_i].strip() == "Y":  # test issues are not real listings
            continue
        role: Role = "reference" if fields[etf_i].strip() == "Y" else "candidate"
        out.append(
            Instrument(
                market="US",
                symbol=fields[sym_i].strip(),
                role=role,
                name=fields[name_i].strip(),
            )
        )
    return out


def parse_idx_screener(symbols: list[str]) -> list[Instrument]:
    """Build IDX instruments from the Yahoo screener's EQUITY symbols.

    The screener returns common equities only, so every symbol is a candidate;
    the market index ``^JKSE`` is folded in as a reference.
    """
    instruments = [Instrument(market="IDX", symbol=MARKET_INDEX["IDX"], role="reference")]
    instruments.extend(Instrument(market="IDX", symbol=s, role="candidate") for s in symbols)
    return instruments


# -- the provider's wire form -------------------------------------------------

# A US share class is written with a dot in the Nasdaq listing files and with a
# dash by the provider: ``BRK.B`` is silence, ``BRK-B`` is Berkshire Hathaway
# (#105). 23 US listings — Berkshire, Brown-Forman, Heico, Moog, Molson Coors,
# Lennar among them — resolved as nothing every night for this alone.
#
# The Nasdaq form is the *identity*: the enumeration, the store's bars, the
# universe rows and every derived stream are keyed by it, and rewriting it in
# the listing file would rename symbols mid-history. So the dash exists only on
# the wire, applied where the request is issued and nowhere above.
#
# A *class* suffix is a single letter; a Yahoo *exchange* suffix is longer
# (``BBCA.JK``), and IDX's whole enumeration carries one — matching only the
# single-letter form leaves that market untouched.
_SHARE_CLASS = re.compile(r"[A-Z]+\.[A-Z]")


def provider_symbol(symbol: str) -> str:
    """The form the provider answers to for ``symbol``.

    Identity for everything but a dotted US share class, which becomes the
    provider's dash form. Applied at the request itself, so callers keep the
    Nasdaq symbol as the name for the thing.
    """
    if _SHARE_CLASS.fullmatch(symbol):
        return symbol.replace(".", "-")
    return symbol


# -- pacing -------------------------------------------------------------------


class Pacer:
    """Paces requests to at most ``rate_per_sec``, in aggregate across threads.

    Time is injectable so tests drive it in virtual time — ``sleep`` may advance
    a fake clock rather than block.

    The rate is a property of the *provider*, not of a caller, so with several
    resolves in flight (:func:`resolve_all`) the cap has to hold across all of
    them at once. :meth:`wait` therefore hands each caller its own slot: under
    the lock it reads the clock and claims the next free instant, and only then —
    outside the lock — sleeps until that instant arrives. Claiming is serialised,
    so N workers get N slots one interval apart and the aggregate never exceeds
    the cap; waiting is not, so the workers' sleeps overlap instead of summing,
    which is the whole point of running them concurrently.
    """

    def __init__(
        self,
        rate_per_sec: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = 1.0 / rate_per_sec
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._monotonic()
            slot = max(now, self._next_allowed)
            self._next_allowed = slot + self._min_interval
        delay = slot - now
        if delay > 0:
            self._sleep(delay)


# -- the source ---------------------------------------------------------------


class Source:
    """Composes a raw :class:`SourceClient` with pacing, backoff and the
    unresolved-not-absent resolution policy."""

    def __init__(
        self,
        client: SourceClient,
        *,
        rate_per_sec: float = DEFAULT_RATE_PER_SEC,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._pacer = Pacer(rate_per_sec, monotonic=monotonic, sleep=sleep)
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base

    def enumerate(self, market: str) -> list[Instrument]:
        """Enumerate a market's instruments, paced as one request."""
        self._pacer.wait()
        return self._client.enumerate(market)

    def pause(self, seconds: float) -> None:
        """Stop asking for ``seconds`` — the sweep's rest (issue #104).

        Waiting *between* requests is the pacer's job; this is waiting between
        whole passes of a pull, which the pacer knows nothing about. It goes
        through the source's injected clock for the same reason every other wait
        does: a test drives the rest in virtual time rather than sleeping.
        """
        self._sleep(seconds)

    def resolve(self, symbol: str, start: date | None = None) -> Resolution:
        """Fetch a symbol's bars, paced and backed off, as a result type.

        Silence — an empty result *or* a persistent 429, indistinguishable by
        spec §3.2 — is retried with exponential backoff up to ``max_attempts``.
        If it never yields bars the result is ``unresolved``, never ``absent``.

        A *stated* refusal is the exception: the provider has answered, so there
        is nothing to wait out. It returns ``refused`` on the first attempt
        rather than burning the full retry budget and its backoff sleeps on a
        listing that will never resolve.

        ``start`` is the incremental window (spec §3.6, issue #100): ``None`` is
        a cold start (full history), a date fetches from that session forward.
        The refusal can only surface on the cold start — passing ``start`` sets
        the provider's ``period`` to ``None``, so a refused listing collapses
        into silence, which is why the caller persists the verdict instead of
        re-probing it every night.
        """
        delay = self._backoff_base
        throttled = False
        for attempt in range(1, self._max_attempts + 1):
            self._pacer.wait()
            try:
                bars = self._client.fetch(symbol, start)
            except RateLimitedError:
                # A 429 is silence too — back off and retry. It is *recorded*
                # silence, though: unlike an empty answer the provider named
                # this one, so the verdict carries which it was (issue #104).
                bars, throttled = [], True
            except PermanentlyUnavailableError:
                return Resolution(symbol, "refused", [])
            if bars:
                return Resolution(symbol, "resolved", list(bars))
            if attempt < self._max_attempts:
                self._sleep(delay)
                delay *= 2
        return Resolution(symbol, "unresolved", [], throttled=throttled)

    def resolve_labels(self, symbol: str) -> LabelResolution:
        """Fetch a symbol's sector and industry, paced and backed off.

        Both labels arrive in one ``.info`` request (spec §3.1). Silence — an
        empty result *or* a persistent 429 (spec §3.2) — is retried with the
        same exponential backoff as bars; a result missing *either* label is
        treated as silence too, because a name with no industry cannot be placed
        on the axis (spec §3.3). If it never yields both labels the result is
        ``unresolved`` and the cached value is left untouched.
        """
        delay = self._backoff_base
        for attempt in range(1, self._max_attempts + 1):
            self._pacer.wait()
            try:
                info = self._client.fetch_info(symbol)
            except RateLimitedError:
                info = {}  # a 429 is silence too — back off and retry
            sector = (info.get("sector") or "").strip()
            industry = (info.get("industry") or "").strip()
            if sector and industry:
                return LabelResolution(symbol, "resolved", sector, industry)
            if attempt < self._max_attempts:
                self._sleep(delay)
                delay *= 2
        return LabelResolution(symbol, "unresolved")


class YFinanceSourceClient:
    """The real network boundary: Yahoo (via yfinance) plus the Nasdaq listing
    files. The only code in the system that makes an outbound request.

    Third-party imports are deferred to the methods so importing this module —
    and every test above it — needs neither ``yfinance`` nor a network. This is
    the class a fake stands in for at the seam; nothing else does I/O.
    """

    def enumerate(self, market: str) -> list[Instrument]:
        if market == "US":
            return parse_us_listings(
                _http_get(NASDAQ_LISTED_URL), _http_get(OTHER_LISTED_URL)
            )
        if market == "IDX":
            return parse_idx_screener(self._screen_idx())
        raise ValueError(f"unknown market {market!r}")

    def fetch(self, symbol: str, start: date | None = None) -> list:
        """Download a symbol's bars. Empty on silence; raises on a 429 or a
        stated refusal.

        The request goes out under :func:`provider_symbol` — the dash form for a
        US share class (#105) — while everything above keeps the Nasdaq symbol.

        Goes through ``Ticker.history`` rather than ``yfinance.download``:
        ``download`` catches everything the fetch raised, prints it, and hands
        back an empty frame, which flattens a refusal the provider *stated* into
        the same silence a throttled request produces — the one distinction
        worth keeping. ``history`` lets the typed error through, so a listing
        Yahoo will not serve is answered once instead of retried four times.

        ``start`` picks the request window (spec §3.6, issue #100). ``None`` is a
        cold start — ``period="max"``, the full history — and is the *only*
        request that can draw the stated refusal: yfinance raises
        ``YFInvalidPeriodError`` inside ``elif period and period not in
        validRanges``, and passing ``start`` sets ``period`` to ``None``, so the
        branch never fires. A date fetches incrementally from that session
        forward; the caller always overlaps stored history so a healthy fetch
        still returns rows (rule 5), and persists the refusal verdict off the
        cold start rather than trying to reconstruct it here.

        Only two of the typed errors are special: a 429 is retryable, and a
        *stated* refusal (``YFInvalidPeriodError`` — "period 'max' is invalid")
        is answered once (spec §3.2). Every other error is the silence
        ``download`` used to swallow — a dead or delisted ticker raises
        ``YFPricesMissingError`` where ``download`` returned an empty frame, and
        that is exactly the ambiguous emptiness §3.2 is about, retried as
        unresolved. Surfacing it as an exception instead would let one bad
        listing kill the whole pull, which is what reopened issue #47.
        """
        import yfinance as yf

        # yfinance swallows fetch exceptions by default and only logs them; this
        # asks for the exception itself, which is the whole point of the call.
        yf.config.debug.hide_exceptions = False
        try:
            # A cold start asks for the whole history; an incremental fetch asks
            # from ``start`` forward, which leaves ``period`` unset (issue #100).
            history = yf.Ticker(provider_symbol(symbol)).history
            frame = (
                history(period="max", auto_adjust=False)
                if start is None
                else history(start=start, auto_adjust=False)
            )
        except Exception as exc:  # yfinance raises its own exception types
            if type(exc).__name__ == "YFRateLimitError":
                raise RateLimitedError(symbol) from exc
            if type(exc).__name__ == "YFInvalidPeriodError":
                raise PermanentlyUnavailableError(f"{symbol}: {exc}") from exc
            return []  # any other fetch error is silence — unresolved, not fatal
        if frame is None or frame.empty:
            return []  # silence — surfaced as unresolved, never absent
        # A single-symbol download can still carry a MultiIndex column axis
        # (field, symbol); flatten to the bare field names parse_bars expects.
        if frame.columns.nlevels > 1:
            frame = frame.droplevel(1, axis=1)
        return frame.reset_index().to_dict("records")

    def fetch_info(self, symbol: str) -> dict:
        """Fetch a symbol's ``.info``. Empty on silence; raises on a 429.

        ``sector`` and ``industry`` ride in the one dict (spec §3.1); only those
        two keys are load-bearing, but the whole dict is returned so the policy
        above decides what "resolved" means.
        """
        import yfinance as yf

        try:
            info = yf.Ticker(provider_symbol(symbol)).info
        except Exception as exc:  # yfinance raises its own YFRateLimitError type
            if type(exc).__name__ == "YFRateLimitError":
                raise RateLimitedError(symbol) from exc
            raise
        return info or {}

    def _screen_idx(self) -> list[str]:
        """Enumerate every JKT-listed equity, paging the screener (issue #110).

        The screener serves at most :data:`IDX_SCREEN_PAGE` quotes per call, so a
        single request sees only the first page. Ask by ``offset`` until a short
        (or empty) page marks the end, sorting by a stable key so successive
        pages neither skip nor repeat a listing; overlap is deduped defensively
        so a provider that ignores ``offset`` cannot inflate the count.
        """
        import yfinance as yf
        from yfinance import EquityQuery

        query = EquityQuery("eq", ["exchange", "JKT"])
        seen: set[str] = set()
        symbols: list[str] = []
        offset = 0
        while True:
            result = yf.screen(
                query, offset=offset, size=IDX_SCREEN_PAGE,
                sortField="dayvolume", sortAsc=False,
            )
            quotes = result.get("quotes", [])
            for quote in quotes:
                symbol = quote["symbol"]
                if symbol not in seen:
                    seen.add(symbol)
                    symbols.append(symbol)
            if len(quotes) < IDX_SCREEN_PAGE:
                break  # a short or empty page is the last one
            offset += IDX_SCREEN_PAGE
        return symbols


def _http_get(url: str) -> str:
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": "screener/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 (fixed hosts)
        return response.read().decode("utf-8", errors="replace")


def default_source() -> Source:
    """The live source: the real Yahoo/Nasdaq client behind the pacing, backoff
    and unresolved-not-absent policy (spec §3.3). What the scheduled run and
    run-on-open drive; tests inject a fake :class:`Source` instead."""
    return Source(YFinanceSourceClient())


def resolve_all(
    source: Source,
    symbols: Iterable[str],
    *,
    workers: int = DEFAULT_RESOLVE_WORKERS,
    start_for: Callable[[str], date | None] | None = None,
) -> Iterator[Resolution]:
    """Resolve many symbols concurrently, yielding each result as it lands.

    The policy above is untouched: every symbol still goes through
    :meth:`Source.resolve`, so unresolved-not-absent, the once-only answer to a
    stated refusal, and per-symbol backoff on silence (spec §3.2/§3.3) all hold
    exactly as they did sequentially. The only change is how many are in flight,
    and :class:`Pacer` keeps the aggregate rate at the same cap regardless.

    ``start_for`` maps a symbol to its incremental start (spec §3.6, issue #100):
    a symbol with stored bars fetches from ``last_stored − 20 sessions``, a
    cold-start symbol from ``None`` (full history). Left unset every symbol is a
    cold start, which is the pre-incremental behaviour.

    Results arrive in **completion order, not input order** — a symbol that
    burns its full retry budget lands long after ones queued behind it. Callers
    that need input order re-key on :attr:`Resolution.symbol`.

    Only ``2 * workers`` symbols are ever submitted at once, and each result is
    yielded before another is queued. A completed future holds a symbol's entire
    price history, so submitting all ~7,300 up front would let a fast provider
    pile the whole market's bars in memory ahead of a slower consumer writing
    them to the store. The sliding window bounds that to the pool's own depth,
    and hands the caller its results as fast as they complete either way.

    ``workers=1`` skips the pool entirely and runs the plain sequential loop.
    """
    def resolve_one(symbol: str) -> Resolution:
        return source.resolve(symbol, start_for(symbol) if start_for else None)

    if workers <= 1:
        for symbol in symbols:
            yield resolve_one(symbol)
        return

    remaining = iter(symbols)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="resolve") as pool:
        pending = {pool.submit(resolve_one, s) for s in islice(remaining, workers * 2)}
        while pending:
            done: set[Future[Resolution]]
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                yield future.result()
                for symbol in islice(remaining, 1):
                    pending.add(pool.submit(resolve_one, symbol))


def sweep_silence(
    source: Source,
    symbols: Iterable[str],
    *,
    pauses: Sequence[float] = SWEEP_PAUSES,
    workers: int = SWEEP_WORKERS,
    start_for: Callable[[str], date | None] | None = None,
    on_rest: Callable[[float, int], None] | None = None,
) -> Iterator[Resolution]:
    """Re-ask a pull's silent symbols, resting first (issue #104).

    Silence that survived a symbol's own retries is not, on this provider,
    reliably a fact about the symbol: at the end of a long pull it is far more
    often a fact about the *pull*, and the same request answers in full once the
    provider has been left alone for a minute. So the run does not write those
    names off where they fell. It collects them, rests, and asks again — the
    isolation retry that diagnosed the problem, done by the run itself.

    Yields **one final resolution per symbol handed in** — the verdict as of the
    last rest, which supersedes the one the pull reached. Most are unchanged;
    the caller applies each as a revision rather than an addition, so a symbol is
    counted, logged and ingested exactly once however many times it was asked.
    A symbol yields as soon as it is answered — resolved, or refused — and is not
    carried into a later rest, because no amount of waiting improves on an
    answer. Only silence is carried, and it is yielded after the last one.

    Each entry of ``pauses`` buys one rest and one pass over what is still
    silent, so the sweeps stop early when the silence does. ``start_for`` is the
    pull's own incremental window (spec §3.6), passed through unchanged — a
    recovered symbol appends where it left off rather than re-downloading ten
    years. ``on_rest`` is called with the pause and how many symbols are about to
    be re-asked, *before* the wait: five silent minutes on stdout is the
    wedged-or-working ambiguity the heartbeat exists to break (issue #96).
    """
    silent = list(symbols)
    for attempt, pause in enumerate(pauses, 1):
        if not silent:
            return
        if on_rest is not None:
            on_rest(pause, len(silent))
        source.pause(pause)
        last_rest = attempt == len(pauses)
        still_silent: list[str] = []
        for resolution in resolve_all(
            source, silent, workers=workers, start_for=start_for
        ):
            if resolution.status == "unresolved" and not last_rest:
                still_silent.append(resolution.symbol)
            else:
                yield resolution
        silent = still_silent


def resolve_market(
    source: Source, market: str, *, workers: int = DEFAULT_RESOLVE_WORKERS
) -> tuple[list[Instrument], list[Resolution]]:
    """Enumerate a market and resolve its candidates.

    References (the index, US ETFs) are enumerated but not part of the
    resolution count that the run's completeness gate reads — the gate measures
    the *tradeable* enumeration (spec §3.4 rule 7). Returns the full instrument
    list and one :class:`Resolution` per candidate, in enumeration order —
    :func:`resolve_all` yields in completion order, and re-keying here keeps this
    function's result a positional match for its candidate list.
    """
    instruments = source.enumerate(market)
    candidates = [i for i in instruments if i.role == "candidate"]
    by_symbol = {
        r.symbol: r
        for r in resolve_all(source, [i.symbol for i in candidates], workers=workers)
    }
    return instruments, [by_symbol[i.symbol] for i in candidates]
