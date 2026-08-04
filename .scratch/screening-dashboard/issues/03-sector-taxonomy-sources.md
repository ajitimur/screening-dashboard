# Free sector/industry classification for IDX and US

Type: research
Status: resolved
Blocked by: —

## Question

What free, machine-readable sector and industry classification exists for IDX and US equities, and how
close does any of it get to the *theme* level?

- **IDX**: the exchange publishes **IDX-IC** (11 sectors, sub-sectors, industries). Is it obtainable
  free and in bulk? How does it map to anything US-comparable? What do free aggregators (Yahoo,
  Stockbit) report for `.JK` tickers, and how complete/accurate is it?
- **US**: what free sources carry sector/industry (Yahoo's own taxonomy, SIC codes via SEC, any free
  GICS-like mapping)? GICS itself is licensed — confirm what is and isn't usable.
- **Cross-market comparability**: can IDX and US names be placed on one sector axis, or must the
  rotation view be per-market? This directly shapes the sector model ticket.
- **Theme**: "AI", "nickel downstream", "GLP-1", "uranium" are not in any standard taxonomy. Survey
  what free options exist at all — thematic ETF holdings as a proxy, curated public lists, correlation
  clustering, LLM tagging of company descriptions. For each: cost, freshness, and how it would be kept
  current. This is scouting the option space, not choosing.

Deliver: what's available per market, completeness/accuracy notes, and an honest read on whether a
free theme layer is viable in v1 or should be flagged as a scope risk.

## Answer

Findings: [`research/03-sector-taxonomy.md`](../research/03-sector-taxonomy.md). Empirically tested,
not just documented.

**Cross-market comparability is solved — and better than expected.** Yahoo Finance applies Morningstar's
GECS taxonomy (11 sectors / 145 industries) *identically* to `.JK` and US tickers. Measured coverage:
**319/320 sampled tickers returned a sector (99.7%)** across 100 liquid IDX + 100 liquid US + 60 random
small-cap IDX + 60 random small-cap US. The two misses were a suspended name (`SRIL.JK`) and a delisted
one (`X`) — so a missing sector is a *delisting signal*, not a coverage gap. **One sector axis spans both
markets, with no mapping table and no GICS exposure.**

**IDX-IC is not usable as a feed.** `idx.co.id` sits behind Cloudflare bot protection — 403 on the
IDX-IC page, both JSON APIs, the PDF, and even `robots.txt`, from two egress IPs and via a text proxy.
It is realistically a hand-maintained static file. Two corrections to this ticket's own premise: IDX-IC
has **12** sectors, not 11 (the 12th is Listed Investment Products), and it is **not 1:1 mappable** to
Morningstar — its "Infrastructures" sector absorbs telecom + toll roads + utilities, which Morningstar
splits three ways. Since Morningstar already covers IDX, IDX-IC is not needed.

**GICS confirmed out**, on S&P DJI/MSCI's own disclaimer: the Information "may not be used to create
derivative works … indices, databases, risk models, analytics, software." That is precisely this use
case. Corollary: Wikipedia's S&P 500 sector columns are GICS and do not become free by being on
Wikipedia.

**SEC SIC verified working** — 444 codes scraped from the SEC list, `data.sec.gov/submissions/CIK*.json`
returns `sic`/`sicDescription`, `company_tickers.json` gives the ticker map. Free and licence-clean, but
US-only, coarse, and self-reported. Useful as a cross-check, not as the primary axis.

### The operational finding that shapes the build

**Yahoo rate-limits hard, and it fails as silence.** After ~200 `.info` calls Yahoo returned
`YFRateLimitError` for ~5 minutes — including for `AAPL`. A first pass reported "0% sector coverage"
purely from throttling; the same sample at 2s spacing with backoff returned 100%. The screener payload
carries **no** sector/industry fields (verified across 2,090 quote records), so sector costs **one
request per symbol** — 1–2 hours wall-clock for a full refresh.

Two consequences, both non-negotiable:
- Sector must be **cached and refreshed incrementally**, never re-pulled wholesale nightly.
- The implementation **must distinguish "throttled" from "no sector"**, or it will silently null out
  good data. Note this generalises: any Yahoo-backed field can fail as silence.

**Also flagged for ticket 05:** Yahoo enumerates only **840** IDX instruments against ~950 listed. That
gap needs reconciling in the universe definition.

### Theme layer — the honest read

Four options surveyed with cost/freshness/maintenance; none chosen (that is ticket 07's call).
Empirically: ARK serves plain same-day CSV and SSGA serves real XLSX, but **iShares, Global X and
VanEck all return HTML/redirects** — three of six issuers need bespoke scrapers and break out of the
box. SEC N-PORT is the clean universal fallback but is quarterly with ~60-day lag, far too stale to
define a theme.

**On IDX, plainly: there is no free thematic ETF proxy, because IDX has no thematic ETF layer.** Its 60+
ETFs are index/sector trackers (LQ-45, IDX30, SRI-KEHATI, Consumer, Financial, SOE) — no nickel,
EV-battery or AI fund exists. Only correlation clustering (free, both markets, but yields unnamed and
unstable clusters) or LLM tagging of business descriptions (`longBusinessSummary` present for >99% of
both markets; ~$1.75–3.50 per full pass at Haiku 4.5 via the Batch API) can produce IDX themes at all.

**So the scope risk is not "themes" — it is theme *parity* across markets.** US-only themes are free and
buildable; both-markets themes require either a small paid LLM line item or hand-curation. Against the
map's "both markets from day one" constraint, this needs an explicit ruling — carried to ticket 07.

### Unverified

Marked in the file: the IDX-IC 12/35/69/130 counts (Indonesian secondary sources; IDX's own PDF
unreachable), sectors.app pricing (bot-blocked), and Yahoo's licensing posture for redistribution —
the last matters only if this app ever stops being personal.
