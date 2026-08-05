"""The source client: the one module that touches the network (spec §3.1).

It does two things and only two things reach the network through it:

- **enumerate** a market's symbols, deriving each instrument's ``role``
  (candidate vs reference) at enumeration — US from the Nasdaq listing files'
  ETF flag, IDX from the Yahoo screener, each market's index folded in as a
  reference; and
- **resolve** a symbol to its bars, paced and backed off, returning a *result
  type* — never a bare list.

The load-bearing behaviour is a failure mode, not a feature. **Yahoo fails as
silence** (spec §3.2): a throttled request returns an empty result that is
byte-identical to a genuinely dead name. No per-symbol care can separate the two
(spec §3.4 rule 5), so the only robust move is to make the ambiguous signal
non-actionable: an empty result is ``unresolved`` and is retried with backoff —
it is *never* reported as ``absent``. Absence requires positive evidence (real
bars failing the density gate, spec §3.4 rule 6), which lives above this module.

Everything above this boundary sees a :class:`Resolution`, never an empty list,
and every test fakes *this* boundary — nothing else needs the network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

from pydantic import BaseModel

# Pacing: 12 requests/second with exponential backoff on 429. Measured
# (spec §3.3): unthrottled returns only 52.9% of the US universe while blaming
# the losses on delisting; 12 req/s gives 99.93% coverage with zero 429s.
DEFAULT_RATE_PER_SEC = 12
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE = 1.0

# One index per market, ingested like anything else but never rankable — its
# role is ``reference`` (spec §2, §4.9).
MARKET_INDEX = {"US": "^IXIC", "IDX": "^JKSE"}

# The Nasdaq Trader listing files (spec §3.1): common stocks plus the ETF flag
# that separates funds. Served over HTTPS, pipe-delimited, with a trailing
# "File Creation Time" footer line.
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

Role = Literal["candidate", "reference"]
ResolutionStatus = Literal["resolved", "unresolved"]


class RateLimitedError(RuntimeError):
    """A request was throttled (HTTP 429). The caller backs off and retries."""


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
    """

    symbol: str
    status: ResolutionStatus
    bars: list = field(default_factory=list)


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

    def fetch(self, symbol: str) -> list:
        """Return the symbol's bars, or an empty list for silence. Raises
        :class:`RateLimitedError` on a 429."""

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


# -- pacing -------------------------------------------------------------------


class Pacer:
    """Paces requests to at most ``rate_per_sec``.

    Time is injectable so tests drive it in virtual time — ``sleep`` may advance
    a fake clock rather than block.
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

    def wait(self) -> None:
        now = self._monotonic()
        delay = self._next_allowed - now
        if delay > 0:
            self._sleep(delay)
            now = now + delay
        self._next_allowed = now + self._min_interval


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

    def resolve(self, symbol: str) -> Resolution:
        """Fetch a symbol's bars, paced and backed off, as a result type.

        Silence — an empty result *or* a persistent 429, indistinguishable by
        spec §3.2 — is retried with exponential backoff up to ``max_attempts``.
        If it never yields bars the result is ``unresolved``, never ``absent``.
        """
        delay = self._backoff_base
        for attempt in range(1, self._max_attempts + 1):
            self._pacer.wait()
            try:
                bars = self._client.fetch(symbol)
            except RateLimitedError:
                bars = []  # a 429 is silence too — back off and retry
            if bars:
                return Resolution(symbol, "resolved", list(bars))
            if attempt < self._max_attempts:
                self._sleep(delay)
                delay *= 2
        return Resolution(symbol, "unresolved", [])

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

    def fetch(self, symbol: str) -> list:
        """Download a symbol's bars. Empty on silence; raises on a 429."""
        import yfinance as yf

        try:
            frame = yf.download(
                symbol, period="max", auto_adjust=False, progress=False, threads=False
            )
        except Exception as exc:  # yfinance raises its own YFRateLimitError type
            if type(exc).__name__ == "YFRateLimitError":
                raise RateLimitedError(symbol) from exc
            raise
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
            info = yf.Ticker(symbol).info
        except Exception as exc:  # yfinance raises its own YFRateLimitError type
            if type(exc).__name__ == "YFRateLimitError":
                raise RateLimitedError(symbol) from exc
            raise
        return info or {}

    def _screen_idx(self) -> list[str]:
        import yfinance as yf
        from yfinance import EquityQuery

        result = yf.screen(EquityQuery("eq", ["exchange", "JKT"]), size=250)
        return [q["symbol"] for q in result.get("quotes", [])]


def _http_get(url: str) -> str:
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": "screener/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 (fixed hosts)
        return response.read().decode("utf-8", errors="replace")


def resolve_market(source: Source, market: str) -> tuple[list[Instrument], list[Resolution]]:
    """Enumerate a market and resolve its candidates.

    References (the index, US ETFs) are enumerated but not part of the
    resolution count that the run's completeness gate reads — the gate measures
    the *tradeable* enumeration (spec §3.4 rule 7). Returns the full instrument
    list and one :class:`Resolution` per candidate.
    """
    instruments = source.enumerate(market)
    candidates = [i for i in instruments if i.role == "candidate"]
    resolutions = [source.resolve(i.symbol) for i in candidates]
    return instruments, resolutions
