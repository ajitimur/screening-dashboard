# Qullamaggie Screening Dashboard — v2 Frontend Spec

**Status:** buildable. Assembled from the nineteen resolved tickets of
[the v2 wayfinding map (#52)](https://github.com/ajitimur/screening-dashboard/issues/52) by
[Assemble the v2 frontend spec (#72)](https://github.com/ajitimur/screening-dashboard/issues/72).

This document is written so a build session can work from it **without re-reading the map**. Every
section links back to the ticket that owns the decision; the ticket holds the reasoning, the
measurements, and the rejected alternatives. Where a later ticket amended an earlier one, this spec
carries **the current answer only** — the amendment chain is recorded in
[§12](#12-the-amendment-chain) so nobody re-derives a superseded decision from an old thread.

Where a decision rests on something unverified or knowingly defective, it is marked **⚠** rather
than presented as settled. Those are collected in [§11](#11-known-defects-and-open-risks).

The v1 record is **PRD [#26](https://github.com/ajitimur/screening-dashboard/issues/26)** and
[`v1-spec.md`](v1-spec.md); `§n` citations are to the v1 PRD unless stated. v1's screen spec (§5)
**stands as the v1 record** — v2 knowingly diverges from it rather than amending it.

**Reference material** (read-only, none of it is depended on at build time):

| Asset | Where |
|---|---|
| The reacted-to shell prototype | `.scratch/screening-dashboard/prototypes/59-app-shell/index.html` (on `main`) |
| q-scanner-v2 computation fact sheet | `docs/research/q-scanner-computations.md`, branch `research/q-scanner-computations` |
| Tailwind v4 token setup reference | `docs/research/tailwind-token-setup.md`, branch `research/tailwind-token-setup` |
| The reference app itself | `/Users/ajitimur/Projects/q-scanner-v2` — **reference only**, never a dependency; the two repos drift freely from here |

---

## 1. Scope

### 1.1 What v2 is

A **replacement frontend** for the screening dashboard that adopts q-scanner-v2's information
architecture wholesale — the screen inventory, the navigation model, the chart-opening idiom, the
design tokens — expressed in Tailwind v4, against a backend grown from seven endpoints to nine to
feed it.

v2 is a **frontend effort with a backend contract attached**. Backend *contract* design is in this
spec; backend *implementation* is the implementing effort's work, ordered by [§10](#10-migration-and-rollout).

It is **not a reskin**. v1's Workbench dissolves, `Boards` is renamed Leaders, and a genuinely new
composite home screen — the Board — arrives.

### 1.2 Out of scope

Compiled from the eight tickets that ruled something out. None of these is deferred v2 work; each was
consciously ruled off the route. They return only as fresh efforts.

| Ruled out | Why | Owner |
|---|---|---|
| **Responsive tablet/phone posture** — breakpoints on the Setups grid, the Board rail, the wide tables, the chart sheet | The away-from-desk need was confirmed **non-existent**; the dashboard is opened at one desk on a ≥1280 display by one person | [#66](https://github.com/ajitimur/screening-dashboard/issues/66) |
| **24M lookback** | `store.py:174` retains exactly 2 years; 24M needs the full window with zero slack — a retention-window bump or computation from bars. Data-retention infrastructure, not spec work | [#63](https://github.com/ajitimur/screening-dashboard/issues/63) |
| **Position sizer** (account + risk% inputs, shares / risk-per-share / position value) | Trade execution, not screening. Its output line — *"per the rules this is NO TRADE"* — is exactly what §4.6 forbids and what the verdict badge was stripped of colour to avoid | [#57](https://github.com/ajitimur/screening-dashboard/issues/57) |
| **Verdict-labeling buttons** and the write endpoint behind them | A detector-training feedback loop needing a write path, a store and a labeling vocabulary that `READY` no longer belongs to. Recorded honestly as the one thing the reference does that this repo genuinely lacks | [#57](https://github.com/ajitimur/screening-dashboard/issues/57) |
| **Fixing the sector taxonomy** (effective-period labels, IDX-IC parsing) | A data-sourcing effort with its own source question; it would swallow this map exactly as a rubric refit would | [#58](https://github.com/ajitimur/screening-dashboard/issues/58) |
| **Wiring CI** for the openapi → types check | This repo has no CI at all. Standing it up is toolchain work past a spec-plus-prototype destination; the spec states the requirement and the command ([§4.9](#49-keeping-the-contract-honest)) | [#58](https://github.com/ajitimur/screening-dashboard/issues/58) |
| **Standing up ESLint + `eslint-plugin-jsx-a11y`** | Same shape: no lint infrastructure exists. `vitest-axe` in the existing suites covers the same ground without a new toolchain | [#67](https://github.com/ajitimur/screening-dashboard/issues/67) |
| **A browser / visual-regression tier** | Human-reviewed screenshots of a built artifact are this effort's idiom for layout, frame, tokens and the rail collapse. Automated visual regression is a separate effort | [#60](https://github.com/ajitimur/screening-dashboard/issues/60) |
| **Star-rubric recalibration** | The Board's ≥3.5★ cut makes a rubric cut load-bearing, which §4.7 says reopens validation. Accepted cold as a known defect (**⚠** [§11.1](#111-the-35-cut-is-load-bearing-on-an-unvalidated-rubric)) | [#53](https://github.com/ajitimur/screening-dashboard/issues/53) |
| **The digest as an app surface** — a fifth tab, a Board rail panel, or any link or mention | The operator has essentially never read the file, so the "most actionable event of the night" case is a claim about a reader that does not exist. The silence is deliberate | [#70](https://github.com/ajitimur/screening-dashboard/issues/70) |
| **Stopping the pipeline writing the digest** | A change to v1's backend, past a destination of a spec plus a prototype. The file keeps being written at `data/digests/<market>/<session>.md`, unchanged | [#70](https://github.com/ajitimur/screening-dashboard/issues/70) |
| **Industry-filtered sector detail** | Detail is per-sector; an industry row drills into its **parent sector** | [#64](https://github.com/ajitimur/screening-dashboard/issues/64) |
| **Per-name reject history** | Real future want, but universe hygiene rather than screening; addable later from the same detector without disturbing anything here | [#53](https://github.com/ajitimur/screening-dashboard/issues/53) |
| **Implementing this spec** | The map's destination was the spec plus a reacted-to prototype. The build is a separate effort | [#52](https://github.com/ajitimur/screening-dashboard/issues/52) |

### 1.3 Standing constraints

- **Desktop only**, design target **≥1280px**. Below that, bare horizontal overflow — no media
  queries, no floor wall, no notice. `index.html`'s `width=device-width, initial-scale=1.0` meta
  stays: it declines to lie about being fixed-width, and is not a mobile claim.
  ([#66](https://github.com/ajitimur/screening-dashboard/issues/66))
- **One user, one desk, one process.** Root `npm start` is `npm run build && uvicorn
  screener.app:app`. No CI, no deploy pipeline, no environments, no flag infrastructure.
- **Two markets** (IDX, US) on different clocks, with wildly asymmetric populations — the asymmetry
  is a first-class design input, not an edge case.
- **The backend stays a set of thin reads of a published run.** Nothing is computed at request time
  that the run could have published. (The one existing exception, the per-symbol chart read, is
  unchanged.)
- **Tailwind v4**, not the reference's inline `style={{}}` + `theme.ts` idiom.

### 1.4 The phase-1 / phase-2 boundary

This is the single most load-bearing rule in the spec, and it is a **field-availability** split, not
a rollout split. ([#58](https://github.com/ajitimur/screening-dashboard/issues/58),
[#61](https://github.com/ajitimur/screening-dashboard/issues/61))

> **Every phase-2 field is nullable in the contract from day one**, so a phase-1 payload is
> contract-valid rather than contract-violating.
>
> **Every phase-1 shape is drawn complete-in-itself. Every phase-2 field is purely additive.**
> No `PHASE 1` chrome, no empty placeholders, no reserved slots, no "coming soon".
>
> **A phase-1 user sees a finished app and is never told what they are missing.**

Nothing reflows destructively when phase 2 lands. The prototype's `PHASE 1` pill is prototype
scaffolding and does not enter the product.

The phase-2 population, in one place:

| Phase-2 field | Blocked on |
|---|---|
| `verdict` (candidates, leaders, sector members) | Persisting `forming` / `extended` rows — **the single largest P2 pipeline change**, ~8× the US detection rows |
| `rejected` counts (`/api/runs`) | The same detector change |
| `move_pctile` | A `gated`-population percentile this repo cannot compute (no universe-level tradability filter) — **and it has no slot to return to; see [§5.1](#51-board)** |
| `tier`, `rs_pctile`, per-lookback `cutoffs` | Cross-sectional tier banding in the run |
| 18M lookback | Extending `indicators.LOOKBACKS` (fits the 2-year retention with slack) |
| `/api/sector-rrg` in its entirety | A `dates × members` matrix, EWM, a per-date cross-section, plus a second whole-universe pass, retaining a 3-week trail |
| `pct_of_52w_high` | No 52-week high is computed anywhere in `indicators.py` |

---

## 2. Domain vocabulary

Adopting an IA wholesale does not mean adopting its words wholesale. This section is the ubiquitous
language for v2; deviations from it are bugs.

### 2.1 The verdict — what the detector found

([#53](https://github.com/ajitimur/screening-dashboard/issues/53)) A name is graded **only if it
reached detection**. Names filtered by the momentum decile gate beforehand carry no verdict and are
deliberately left unnamed (~920 of 1167 US names on a typical night).

| Term | Meaning | Stored as |
|---|---|---|
| `detected` | `detection.py` emitted a row — the pattern is complete and drawable | rows (existing `detections` table) |
| `forming` | died at an immature test — base too short to judge, no tight cluster yet, price not caught up to the 10/20-day. Comes back tomorrow | rows (**new**, P2) |
| `extended` | died at `base_too_short` because the prior move's peak is 1–2 bars back — the name is making new highs *now*, not basing. *"You missed it"*, not *"not yet"* | rows (**new**, P2) |
| `rejected` | died at a hard gate — no bars, too little history, ADR ≤ 0, no prior move | **nightly count by reason, never rows** |

`detected` / `forming` / `extended` is the persisted enum, three members. `rejected` is a counter,
because it fires 0–3 times a night; its real value is **pipeline health** — a `no_bars` count
jumping from 2 to 400 is an ingest outage announcing itself.

**`verdict: null` means *not evaluated*** — a different fact from `extended`. It occurs on Leaders
rows and sector-detail rows, which show the gated population and a pack respectively, and therefore
contain names the detector never ran on.

**Deliberately not adopted: `READY` / `NEEDS_MORE_TIME` / `NO_SETUP`.** `READY` is a recommendation
wearing an enum's clothes. The v2 terms describe the **pattern's** state, never the trade.

### 2.2 The score — how the detected names are ordered

The star score stays exactly what §4.7 made it: **a pure sort key inside `detected`**, 0–5, computed
at read time, never persisted, never a gate, stop-blind and regime-blind.

**The verdict never comes from the score; the score never becomes a gate.** That split is the whole
of the grade-or-rank decision.

`breakdown` (the eight-row §4.7 arithmetic) rides `detected` rows only and is `null` on
`forming`/`extended` — not trimming, but the fact that the rubric does not define a number there.

### 2.3 Prices, widths and distances

| Term | Meaning | Call |
|---|---|---|
| `trigger_price` | the breakout level | **borrowed** from the reference — v1 had no word for it |
| `stop_price` | the watchlist stop (cluster low) | **borrowed** |
| `stopw_adr` | stop width in ADR multiples | **v1's word, kept** |
| `risk_adr` | the reference's name for `stopw_adr` | **refused** — one quantity, two names; and `stopw_adr` carries §4.6's watchlist-stop meaning |
| `dist_adr` | distance to trigger in ADR multiples | v1's, kept — and promoted to a permanent card stat |
| `adr`, `dollar_volume`, `affordable`, `score`, `decile_ranks` | unchanged from v1 | |
| `entry_quality` | an output of the reference's pattern engine | **refused** — that engine is not being ported. v1's `affordable` keeps the opposite polarity deliberately: it flags the passing minority, since ~92% of the nightly list is wider than the 1.0×ADR cap |
| `move_pctile` | percentile of the prior move | **borrowed as a name, but P2 and unslotted** — see [§5.1](#51-board) |

**Every percentile field names its population** — `universe` / `live` / `gated`. The reference's
percentiles are all over `gated` (live ∧ liquidity ∧ ADR ≥ 4) and this repo applies **no
universe-level tradability filter**. Any phase-1 field computable only over `universe` gets a
different name from the reference's rather than borrowing one. The cautionary case is live already:
the two apps' `breadth` are **different quantities sharing a name**, and nobody noticed until the
fact sheet.

### 2.4 Three senses of "new" — two survive, and they are named apart

([#58](https://github.com/ajitimur/screening-dashboard/issues/58),
[#63](https://github.com/ajitimur/screening-dashboard/issues/63),
[#70](https://github.com/ajitimur/screening-dashboard/issues/70))

| Term | Meaning | Where |
|---|---|---|
| `new_tonight` | newly **detected** — absent from last session's `detected` rows | candidate row (P1); Board hero cards, Setups cards |
| `new_to_leaders` | newly **ranked** — absent from this lookback's top cut last session (`boards.py:108`) | leaders row; scoped to the **active lookback** |
| ~~a break~~ | today's close cleared yesterday's trigger | **the digest only — never reaches the app** ([§1.2](#12-out-of-scope)) |

A third "new" on one screen is the vocabulary failure two tickets spent themselves avoiding; keeping
the digest out is what keeps it at two.

### 2.5 Navigation motions

([#67](https://github.com/ajitimur/screening-dashboard/issues/67),
[#69](https://github.com/ajitimur/screening-dashboard/issues/69))

- **Activation** — the user pressed a control. Focus rules apply ([§8.6](#86-focus)).
- **History navigation** — a destination change with **no activation behind it**: browser back or
  forward. Focus rules deliberately do **not** apply; announcement does.

Both words are needed, because the entire focus decision is *"the rule applies to one and not the
other."*

### 2.6 Taxonomy

Sector labels are yfinance **GECS**, keyed `(market, symbol)` with a single `as_of` and **no
effective period**. Every sector-bearing response carries `taxonomy: "GECS"`. ~75% agreement with the
reference's IDX-IC on IDX names; `Industrials` splits four ways. **⚠** A relabel silently rewrites
history, and the P2 RRG's 3-week trail is what will make that visible for the first time.

---

## 3. The shell

The shell is everything outside the screens, present on every screen.
([#56](https://github.com/ajitimur/screening-dashboard/issues/56),
[#59](https://github.com/ajitimur/screening-dashboard/issues/59))

### 3.1 The frame

**Full-bleed.** Header, regime band and run-status banner span the window; the content column caps at
`--container-shell` (82.5rem / 1320px). The page scrolls. **One scroll context** — nothing is
height-capped.

The reference's centred 1320px card was the more faithful adoption and **lost anyway**, on evidence
the prototype produced rather than argument:

- The Board fills neither frame at 1440×1100 — ~250px of dead space on a healthy US night, far more
  on IDX's two-card night. Inside a floating card that emptiness reads as *the card is short*, which
  invites the reader to think something failed to load. Full-bleed reads as *the page is short*,
  which is a fact about the night.
- At 1280 full-bleed reads **better** than at 1440 (less dead width flanking the content). The card
  has no equivalent improvement — below 1320 it is clipped to `max-width: 100%` and stops being a
  card.
- The card's `height: 100vh` + internal scroll gave two scroll contexts on a screen that already has
  a scrolling table.

### 3.2 Tokens

Declared **CSS-first in an `@theme` block** (Tailwind v4; JS config is legacy and no longer
auto-detected). Open the block with `--color-*: initial` so the custom `red`/`green`/`amber` names do
not collide with Tailwind's stock scales.

**Type scale — the reference's, kept, 9.5px floor and all:**

| Token | px |
|---|---|
| `--text-micro` | 9.5 |
| `--text-label` | 10.5 |
| `--text-meta` | 11.5 |
| `--text-body` | 13 |
| `--text-head` | 15 |
| `--text-stat` | 16 |
| `--text-ticker` | 20 |

The 11px-floor variant was built and rejected: more legible in isolation, but ~8% vertical on a
screen already fighting for density, pushing the Leaders strip toward the fold at 1280.

> **These are design-target values under `min()`, not hard walls.**
> Claiming SC 1.4.4 Resize text ([§8.2](#82-the-claim-in-one-line)) forbids fixed `height` (use `min-height`) and
> **bans `overflow: hidden` on any text container**. A dense board is exactly where fixed-height
> panels tempt, and clipped 9.5px text is the failure 1.4.4 exists to stop.

**Palette — the reference's paper ground, with the neutral ramp and semantic trio darkened.** The
palette is **not** adopted wholesale; the measurement is in [§8.3](#83-contrast--the-measurement-that-decided-the-palette).

| Token | Value | Note |
|---|---|---|
| `--color-bg` | `#e7e4de` | paper ground |
| `--color-surface` | `#f6f4ef` | |
| `--color-card` | `#ffffff` | |
| `--color-border` | `#e8e2d8` | |
| `--color-text` | `#1c1b18` | |
| `--color-text-muted` | **`#6b665c`** | was `#8a857c`; carries **every 9.5px label in the app** |
| `--color-fill-faint` | `#a09a8e` **lifted to ≥3:1 on `bg`** | was `--color-text-faint`; **dead as a text token** — non-text fill only |
| `--color-green` | **`#17703e`** | was `#1f8a4c` |
| `--color-amber` | **`#8a6215`** | was `#c08a2e` |
| `--color-red` | **`#b03d26`** | was `#c8492f` |
| `--color-affordance` | own token at a **3:1** floor | was `underline #b3ab9d`; the ticker's dotted underline |
| sector scale | ten hues, unchanged | see the reachability rule below |
| `--radius-card` | `1.125rem` (18px) | |
| `--shadow-shell` | `0 30px 70px rgba(40,34,24,.20)` | |
| `--container-shell` | `82.5rem` (1320px) | |
| `--font-sans` | Space Grotesk | via `@fontsource`, self-hosted |
| `--font-mono` | IBM Plex Mono | numerics |

**⚠ The reachability gotcha, which fails silently.** Tailwind v4 **tree-shakes `@theme` variables
that no utility class mentions**. The sector scale and the regime pairs are read only from a runtime
`var()`, never from a class, so they are dropped from the emitted CSS and bars and dots render
uncoloured — no error, just no colour. They need `@source inline(...)` or a plain `:root` declaration
**alongside** `@theme`. Confirmed and fixed in the prototype.

**Runtime-selected colour splits three ways** — Tailwind can never build a class from a runtime
string ([#55](https://github.com/ajitimur/screening-dashboard/issues/55)):

| Case | Pattern | Why |
|---|---|---|
| sector colours | CSS variable via inline `style`, read as `bg-(--sector)` | keyed by a backend string with an existing fallback branch; a static map has nothing to emit for an unanticipated sector |
| verdict colours | static class map | the set is closed at three after normalisation |
| bar widths | plain inline `style` | continuous values; no pattern enumerates them |

The reference's style helpers are therefore **rewritten, not deleted** — return type changes from
`CSSProperties` to a class-name string or a CSS-variable style object.

**Two repo gotchas.** `frontend/tsconfig.json` pins an explicit `types` array omitting
`vite/client`, so `import "./index.css"` breaks `tsc -b` until that is added. Vitest stubs CSS to
empty strings, so under jsdom Tailwind classes have no computed styles — assert `toHaveClass`, never
`toHaveStyle`. Inline-style values do survive into the DOM and stay assertable.

**Install** is `tailwindcss` + `@tailwindcss/vite`, the plugin in `vite.config.ts`, and
`@import "tailwindcss"` in one CSS file. No PostCSS config, no autoprefixer, no `content` array, no
init step. The peer range covers this repo's Vite 5.4.2 — **no build-tool upgrade is forced**.

### 3.3 Chrome

**Header strip**, left to right: product name · **as-of session** · tab row · market segmented
control.

**Beneath the header, in this fixed order:**

1. **The regime band — v1's full §4.9 banner, unchanged.** State, the sizing posture *in words*,
   breadth, as-of. **Permanent, on every screen, gates nothing.**
2. **The run-status banner — only when abnormal.** Run-in-progress, run-failed, quarantine/stale.
   Dismissible. Absent on a healthy night.

Both can be present at once on a quarantined night.

**The reference's regime pill is rejected.** It compresses §4.9's posture wording — the very thing
built to keep the banner advisory — into a coloured pill, the same "recommendation carried in the
paint" that stripped colour from the verdict badge.

**Run status must be global**: v1's stale-quarantine banner exists to stop someone trading a stale
session, and hiding it inside one screen means a user sitting on Leaders never sees it.

**Universe size is deliberately not shell chrome.** It lands as the Board's funnel line
([§5.1](#51-board)).

### 3.4 Market, and what a market switch does

Market is a **header segmented control**, not the outer axis. Screens are the primary tab row; market
is the lens held over them. Rejected: market-outer (wastes the header's primary position on a
two-value toggle) and per-screen market state (the populations are asymmetric enough that per-screen
market turns *"why is this screen empty"* into a navigation puzzle rather than a fact about IDX).

**The reset rule, stated as a principle rather than a list:**

> **State that names a specific entity is market-scoped and resets. State that describes view shape
> survives.**

- **Resets**: selected symbol (so the chart sheet closes), sector filter, ticker query, the sector
  drill-down.
- **Survives**: active tab, lookback, sort key, table/grid view, verdict filter.
- **Sector detail falls back to the Sectors list** when that sector has no pack in the new market —
  the *eject*, which is announced ([§8.7](#87-sound-one-alert-three-polite-regions)).

This is a deliberate tightening of v1, which cleared only the selected symbol. Carrying a US-only
sector filter onto IDX leaves a zero-row screen with no hint why.

**Carrying the sector across markets was rejected**: "Energy" in GECS and "Energy" on IDX-IC are
different populations — the taxonomy gap of [§2.6](#26-taxonomy).

### 3.5 URL and history

([#68](https://github.com/ajitimur/screening-dashboard/issues/68))

**The URL carries destinations and only destinations, and it is the single source of truth for
them.**

```
/?market=US&tab=sectors&sector=Energy
```

Three axes and only three: **market**, **tab**, **selected sector on the drill-down**. Everything
else — Leaders lookback, sort key, table/grid toggle, carried filter chips, ticker query, and the
open sheet's symbol — stays in memory and never reaches the bar.

**Defaults are omitted.** A cold open is bare `/`; params appear only as the destination diverges. So
"no params at all" is a permanently valid state rather than something corrected on load.

**Query string, not paths — decided on a production fact.** `backend/screener/app.py:309` mounts
`StaticFiles(directory=dist, html=True)` at `/`, which **404s any path it cannot find on disk**. So
`/us/sectors/energy` works under the Vite dev server and **breaks on reload under `npm start`**
unless the backend grows an SPA catch-all — work ruled out of scope. Pretty paths pay when strangers
read your links, and nobody does. Query params also degrade well: an unknown key is ignorable where
an unknown path segment is a 404. Hash routing is rejected as a workaround idiom for a problem you
would be choosing to have.

**Why deep-linking survives at all**, given the audience of one: **not** shareability — no dashboard
link is ever pasted anywhere, which leaves *"a symbol is not a destination"* unchallenged. What
survives is a daily papercut: **back is a reflex, and with zero history entries it exits the app.**
Reload survival is the cheap second gain.

**Full reconstruction (lookback, sort, chips, query in the URL) is rejected** on the same fact that
saved the minimal form: reconstructing a sort key only pays when someone else opens the link, and it
would force every Leaders control to own a serialisation format and a legacy-value story for
nothing.

**No cold-open persistence.** No `localStorage`, nothing restored on a fresh tab. Market is the
deciding case: two markets on different clocks means *last visited* is a bad predictor of *wanted
now*, and restoring `US` for an IDX morning is worse than a neutral default because it is **wrong
silently**.

**What pushes, and what back does.** Tab change, sector drill-in, **and market switch** all push
history entries.

> On `IDX / Sectors / Energy` you press **US**, land on the US Sectors list with Energy discarded,
> then press back. **Back returns you to `IDX / Sectors / Energy`, sector and all.**

This does **not** contradict the reset rule: the reset rule describes what the market control *does
when pressed*; back does not press the control, it **restores a destination** — the same act as
opening that bookmark. The alternative (market *replaces*) was put and declined because it is the
option that actually misbehaves: it strands you on US at an IDX-era position, the mixed state the
reset exists to prevent. **This is the case a future reader is most likely to "fix" into a bug.**

**The chart sheet is invisible to history.** No entry; back does not close it. Swap-in-place is what
kills the idea — clicking through six tickers is one sheet, so it is six junk entries or none, and
neither reads as *"back closes what I opened."* Esc already does that job. Consequence the build must
honour: **with the sheet open, back navigates**, and the sheet closes as a side effect of the
existing close-on-tab-change / close-on-market-switch rule. No third closing idiom.

**Unhonourable URLs fall back silently and rewrite via `replace`:**

| URL | Resolves to |
|---|---|
| `?market=XYZ` | default market |
| `?tab=workbench` (the dissolved screen) | Board |
| `?sector=Energy` when that market has no such sector | that market's Sectors list |
| `?tab=sectors&sector=` | the Sectors list |

**Never an error** — a typo'd query param is not a backend outage, and the app's one `role="alert"`
is reserved for identity reads. **The `replace` rewrite is load-bearing, not cosmetic**: leaving a
lying URL in the bar means back and forward replay a destination that does not exist. Nothing is
announced about the correction ([§8.7](#87-sound-one-alert-three-polite-regions)).

**The URL is the source of truth, not a mirror.** There is **no `useState` for market, tab or
sector**; one hook reads `location.search`, and setting a destination *is* a `pushState`. The mirror
alternative is rejected — two truths that drift is how back-button bugs are born, and every fix is
another sync direction. Concretely: **`App.tsx:34-35`'s `market`/`screen` `useState` pair does not
survive into v2 in that form.**

**Hand-rolled, no `react-router`.** Its weight is in path matching, nested routes, loaders and
route-level splitting — none of which this design has — and it would hand every screen-level test
suite a provider wrapper and a synthetic entry URL, exactly the per-file plumbing the testing posture
collapsed its fixtures to avoid. If nested routes or code splitting ever arrive, adopting a router is
a contained change: the hook is already the single seam.

**View state persists across a tab round-trip.** Leaders at 3M sorted by ADR → Board → back returns
you to **Leaders at 3M sorted by ADR**, not a reset screen. The shape-vs-entity line already keeps
shape state across the *harder* transition (market switch); a tab round-trip is strictly gentler.

### 3.6 Shell lifecycle

**Run-on-open and its poll move from the dissolving Workbench's `useEffect` into shell lifecycle.**
Dissolving Workbench without rehoming them would silently drop run-on-open.

---

## 4. The backend contract

([#58](https://github.com/ajitimur/screening-dashboard/issues/58), amended by
[#63](https://github.com/ajitimur/screening-dashboard/issues/63))

**Seven endpoints become nine, grown in place, and every one stays an independent thin read of a
published run.**

### 4.1 The shape decisions

- **Grow in place, no `/v2` prefix.** One consumer, shipped from this repo in the same process
  (`app.mount` serves `frontend/dist`, `app.py:308`). Versioning buys compatibility nobody needs.
  Additive-only was the trap: it would leave `/api/candidates` carrying both v1's shape and v2's
  fold, permanently.
- **Independent resources, no screen-shaped composites.** The decisive argument is **ordering**: the
  contract was designed *before* the four layout tickets, so a screen-shaped endpoint would have been
  designed against layouts that did not exist, and every layout revision would become a contract
  revision. It also preserves v1's property that the regime banner never gates the list — now
  permanent chrome on all four screens, so independently fetchable by construction.
- **The Board needs no new endpoint.** This is the load-bearing evidence, not a footnote: the Board
  was the only screen that plausibly justified a composite and turns out to be pure composition.
- **Market stays in the path**, `/api/x/{market}`. A pure consistency call — seven endpoints, an
  `openapi.json` and a generated `schema.d.ts` already exist in that style.

### 4.2 The endpoint set

| Endpoint | Status |
|---|---|
| `GET /api/runs/{market}` | unchanged **+ `rejected` map on the latest run** (P2) |
| `POST /api/runs/{market}` | unchanged |
| `GET /api/regime/{market}` | **unchanged — no new fields** |
| `GET /api/candidates/{market}` | **folded + widened** |
| `GET /api/leaders/{market}` | **renamed** from `/api/boards`; + `sector`/`dollar_volume` (P1), tiers/cutoffs/`rs_pctile` (P2) |
| `GET /api/sectors/{market}` | unchanged |
| `GET /api/sectors/{market}/{sector}` | **new** — the drill-down |
| `GET /api/sector-rrg/{market}` | **new**, P2 entirely |
| `GET /api/chart/{market}/{symbol}` | **+ `?bars=N`** |

**`/api/boards` → `/api/leaders`** (models `Leader` / `LeaderRow` / `LeadersResponse`). Leaving
`/api/boards` behind while *Board* is a different thing entirely is the worst outcome — a future
reader hits `/api/boards` and reasonably assumes it feeds the Board.

**`/api/regime` gains nothing.** v1's full §4.9 banner is kept and the reference's pill rejected, so
`mode` / `sma10_rising` / `sma20_rising` would be growth with no consumer — and the two apps'
`breadth` are already different quantities sharing a name.

**`rejected` lands on `/api/runs`** as `{reason: count}` on the latest run record: a property of the
run, not of the market's regime, and `/api/runs` is the run-health resource the shell already polls.

### 4.3 The candidate row

**Fold `trigger_price`, `stop_price`, `close`, `sector`, `adr`, `dollar_volume`, `decile_ranks` onto
the candidate row — and `/api/chart` keeps them too.**

These fields all exist today, inside the per-symbol bundle at `/api/chart/{market}/{symbol}`
(`ChartFacts`, `SetupOverlay`). They were simply not on the candidate row, so a Setups grid showing
trigger and stop was an N+1 of 27 HTTP calls, **not missing data**.

**The duplication is deliberate.** The chart sheet is opened by click from four screens and must
render header → chart → facts → breakdown as one unit; making it stitch two responses would trade an
N+1 for a join and reintroduce the gating dependency independent resources exist to avoid. **The
detection row is the single source; both endpoints project from it.**

Also on the row:

- **`new_tonight: bool`** — P1. `store.detections_before` already exists (`store.py:539-551`) and
  `boards.py:96-99` already does the analogous per-board diff. No `/api/new-ready` endpoint: the
  reference has one only because its Board renders a standalone panel, and the row-level fact is
  strictly more useful.
- **`verdict: string | null`** — P2.
- **`breakdown: ScoreRow[] | null`** — `null` on `forming`/`extended`.

**All three verdicts come back in one response; the filter is client-side.** No `?verdict=` param —
that keeps the filter instant and the endpoint one resource. **No pagination**, which would break the
client-side filter.

The cost was accepted with a condition, and the condition **discharged**: the US response grows ~8×
at P2 (~2 vs ~216 `forming` names a night), but the payload was always cheap — only *rendering* 216
mini-charts was expensive, and the Setups grid's 60-card cap fixes exactly that
([§5.2](#52-setups)). **So no `?verdict=` param is needed.**

### 4.4 The leaders row

Per-lookback boards, `(-raw_return, symbol)` ordering. **P1 fields include `sector: string | null` and
`dollar_volume: number`** — both cheap adds (`board_symbols` already reads exactly these names' bars
for the ADR column; sector is a `(market, symbol)` store lookup). Without them the phase-1 control bar
would ship with two live controls and two dead ones.

`tier` and `rs_pctile` are nullable row fields (P2). `cutoffs` is a per-lookback block **beside**
`rows`, never repeated on every row (P2). 18M joins the lookback enum at P2; **24M is out of scope**.

### 4.5 Sectors, sector detail, and the RRG

- `GET /api/sectors/{market}` — unchanged; carries `taxonomy: "GECS"`.
- `GET /api/sectors/{market}/{sector}` — member rows with per-lookback returns, per-name decile
  (P1), `verdict` marker (P2), `pct_of_52w_high` (P2). **The sector name needs URL-encoding** — GECS
  labels contain spaces (`Consumer Cyclical`) — spec'd explicitly rather than left to whoever
  implements.
- `GET /api/sector-rrg/{market}` — P2 entirely. Its natural shape is a **series per sector**, not a
  row, because it carries a 3-week trail. Keeping it separate means the phase-1 Sectors screen
  fetches only `/api/sectors` and renders its permanent band with zero knowledge that RRG exists.

### 4.6 `?bars=N` on the chart read

`GET /api/chart/{market}/{symbol}?bars=N`. Default is full history; response shape unchanged;
truncated **from the tail**.

**Spec the ordering explicitly: truncate *after* the session filter, never before.** Truncating first
would let a quarantined pull's bars survive into a 60-bar window.

One endpoint, not a second lightweight `/api/sparkline` — a second endpoint would fork the
"scope bars to the published session" quarantine guard (`app.py:249`) into two places.

**Not required**: hoisting the per-session rank recompute (`store.ranks`, `detection_gate`,
`leave_one_out_sector_shares`, `app.py:250-269`) out of the per-symbol call. It mattered only to make
a hover-prefetch defensible, and hover-open was dropped. A nice-to-have, not a dependency.

### 4.7 The envelope

**Every v2 endpoint carries `market` + `session: date | null`**, same meaning throughout, no
exceptions. `null` means no run has published — an explicit empty state, never a fabricated date.
This is what lets "no run yet" be one case handled once in the shell rather than four per-screen
variants.

**Explicitly outside the envelope**: staleness and run-failure, which stay on `/api/runs`.

### 4.8 Caching — deliberately absent

**The contract says nothing about caching, and the spec says so out loud.** No `ETag`, no
`Cache-Control`. Adding them would put a correctness-critical invariant — never serve a quarantined
session's bars (`app.py:249`) — behind an HTTP cache whose keying nobody has designed. The shared
chart cache is a **frontend** concern, keyed on `(market, symbol, bars)`. Saying this explicitly
stops the implementation effort reading the silence as an invitation.

### 4.9 Keeping the contract honest

The chain is `python backend/scripts/dump_openapi.py` → `frontend/src/api/openapi.json` →
`pnpm gen:types` → `src/api/schema.d.ts`, entirely manual, with **no CI in this repo at all**.

**The requirement**: one command that dumps and generates, plus a check that fails if the working
tree changes afterwards, run whenever a `models.py` response model changes.

**Wiring it is out of scope** ([§1.2](#12-out-of-scope)) and inherited by the implementation effort.

---

## 5. The screens

**Four tabs, one drill-down, and the Workbench dissolves.**
([#56](https://github.com/ajitimur/screening-dashboard/issues/56))

v1's Workbench was not a screen — it was a stack of four screens with no editing. Its candidate list
and chart panel become **Setups**; its sector board becomes **Sectors**; its regime banner and as-of
line become **shell chrome**. v1's `Boards` is renamed **Leaders**, freeing the name **Board** for the
composite home v1 genuinely lacks. **Nothing in v2 is named after the Workbench.**

| Screen | The question it answers | Source | Entry points |
|---|---|---|---|
| **Board** (landing) | "What should I look at tonight?" | **New** — the reference's Board re-expressed | Default landing; nav tab |
| **Leaders** | "Who moved most, over which horizon?" | v1's `Boards`, renamed | Nav tab; Board's "See all →" |
| **Setups** | "Which names are set up, and what does each look like?" | v1's Workbench, split — `CandidateList` + `ChartPanel` | Nav tab; Board's "view charts →" |
| **Sectors** | "Where is money rotating?" | v1's `SectorTable` **and** the reference's RRG, as stacked bands; v1's industry board retained | Nav tab |
| **Sector detail** | "What is inside this pack?" | The reference's `SectorDetailView` | **Drill-down only**; keeps the Sectors tab lit |

**A symbol is not a navigable destination.** There is no symbol page. The chart sheet
([§6](#6-the-chart-sheet)) is the **only** symbol surface in v2 — which is why it inherits the §4.7
score breakdown as its floor.

### 5.0 The verdict on screen

**A filter axis and a neutral typographic badge. No colour.** The reference's red/amber/green
treatment — coloured left borders, `verdictBadgeStyle`, `verdictDotStyle` — is **rejected**.

A badge reading `forming` describes the *pattern's* state, which is exactly the vocabulary chosen so
it would not read as a recommendation, and is compatible with §4.6 (which forbids marking a name as a
*buy*, not naming what the detector found). **A traffic light carries the recommendation back in
through the paint**, undoing in colour what the vocabulary protected.

The distinction that survived an explicit challenge and holds everywhere in this spec:

> **Colouring a number by what it is carries no recommendation. Colouring a name by how good it is
> does.**

So the stop-width bar keeps its green/amber/red fill, and trigger/stop keep directional colour, while
the verdict badge stays neutral.

### 5.1 Board

([#61](https://github.com/ajitimur/screening-dashboard/issues/61)) The Board's job is to **cut**, not
stack — that is the stated reason v1's Workbench failed. Layout is `1fr + 384px`: heroes and strip
left, rail right.

**The hero cut.** `≥3.5★` subset of `detected`, **capped at 4**, sorted **stars descending with
`stopw_adr` ascending as tie-break**, and **no placeholder slots**.

- The cap is the point: ~8 US cards is a second grid, which *is* Setups, reachable by
  "view charts →".
- Stars lead because the score is defined as exactly this — a pure sort key inside `detected`;
  `stopw_adr` breaks ties because two 3.5★ names are genuinely separated by stop width.
- **No placeholder slots.** *"2 more slots — nothing else cleared every gate"* frames a quiet night
  as unfilled capacity, the "broken card" reading full-bleed was chosen to avoid. Two cards then the
  next section is honest.
- **⚠** The cut is `≥3.5★`, corrected from `>3.5★` — on half-star granularity `>3.5` means 4.0+,
  which collapses IDX to **one** card on the market that is already sparsest. See
  [§11.1](#111-the-35-cut-is-load-bearing-on-an-unvalidated-rubric).

**The hero card.**

```
ticker · stars · NEW · sector chip
TRIGGER · STOP · DIST
[ stop-width bar ]  stop N×ADR
```

- **`DIST` (`dist_adr`) is the permanent third stat, not a stand-in for `MOVE`.** It is P1, and it
  answers the one thing trigger and stop do not: *how far away is this tonight*. **`move_pctile` has
  no slot to return to at P2, and that is correct** — it describes the base's history, which is what
  the chart sheet is for.
- The bar is labelled `stop N×ADR`. The quantity is `stopw_adr`; `risk_adr` is refused vocabulary.

**The universe funnel** is one **line under the hero section header**, not a stat panel and not a
rail tile:

```
4,812 listed · 1,196 ranked · 27 detected          (P1)
… · 216 forming · 148 rejected                     (P2, appended)
```

It answers *"is tonight thin, or is the pipeline broken?"* — the same question IDX's two-card night
raises — so it belongs beside the cards.

> **Spec reconciliation.** The Board resolution describes the rail as "two panels at phase 1"
> including a universe/funnel panel, and then separately relocates the funnel to a line beside the
> cards with the reasoning above. The relocation is the later and explicitly-argued statement, so
> this spec takes it: **the phase-1 rail carries one panel.**

**The rail — "Where money is rotating".** Top-5 sectors by shape differential at P1, drawn as
**centre-anchored diverging bars** (left negative, right positive — see
[§8.4](#84-colour-that-carries-meaning)). At P2 the RRG map **appends above** the bars. The header is
a behaviour name, not an artifact name, so it survives the map's arrival unchanged.

**"New tonight" is killed** as a rail panel. A chip carrying no price, stop or sector is a name you
have to go *find*, which is the stacking the Board refuses. **`NEW` is a badge on the row or card
where the name already appears, and nowhere else.**

**The leaders strip.** 1-month only, **10 rows**, columns `ticker · sector · 1M · breadth`, **heroes
included** (no dedup). Consequence recorded: with heroes included the strip is a straight top-10
momentum list, so what keeps it off Leaders' turf is purely **lookback count** (one vs five), not
content — and Leaders owes no de-duplication back. `STATE` is dropped; at P2 the strip **appends** one
neutral `verdict` badge column.

**Dead space.** Fill by **stretching the one element with arbitrary length** — the strip takes
`flex: 1` to the bottom of the left column, shows 10 rows, scrolls internally beyond that. Rail
panels sit at natural height at the top of the right column. **A healthy US night fills the frame
because the strip is genuinely long there; the IDX two-card night is left short on purpose** — that
shortness is exactly what full-bleed was chosen for.

**The rail collapses while the chart sheet is open.** At 1280 with the ~540px sheet docked, the
content area drops to ~740px; against a 384px rail that leaves ~330px, which cannot hold two setup
columns. **The sheet takes the rail's place and the setup grid keeps its two columns** — a chart is
opened constantly, and reflowing the primary content on every open is the worse failure. Rejected:
dropping the setup grid to one column.

### 5.2 Setups

([#62](https://github.com/ajitimur/screening-dashboard/issues/62)) **The grid *is* the screen** — no
rail, no strip, no composite.

**A 3-column card grid, always — never a table.** This is the chart-looking screen you arrive at via
the Board's "view charts →"; a table would make it Leaders with more columns and throw away the
mini-chart that is its whole reason to exist.

**Column count is not fixed — card width is**: `auto-fill, minmax(~360px, 1fr)`. So the grid reflows
to 3 columns at 1440 (content capped at 1320), 2 at 1280, and 2 when the chart sheet is docked.

**Phase 1 renders exactly `detected`** — 5 cards on IDX, ~27 on US — and is complete-in-itself: no
verdict control, no empty axis. At P2 the filter appears as a **single-select** segmented control
defaulting to `detected`, **never an "All"** unioning ~216 `forming` with ~27 `detected`. The Board's
"view charts →" chip is a no-op at P1 and a real carried chip at P2. **The IDX two-card `forming`
night gets no special copy** — the header count is the whole explanation.

**Two controls, and no sort.** Ticker search + sector filter, both rendering as **dismissible chips
when carried in** (the sector chip is how you arrive from Sectors detail). No sort control: the star
score is *the* order, and a sort selector would invite re-ranking around a rubric ruled out of scope
for recalibration. **Fixed order is `stars` desc, `stopw_adr` asc** — identical to the Board's hero
cut, so both screens agree on what "better" means.

Header row: controls left, `N setups · as of {session}` right-aligned, where **N is the true filtered
total, never the rendered count**.

**The card — the Board card's anatomy, plus the mini-chart:**

```
ticker · stars · NEW · sector
TRIGGER · STOP · DIST
[ mini-chart ]
[ stop-width bar ]  stop N×ADR
```

A name looks the same wherever you meet it. `verdict` badge is P2; `move_pctile` is killed;
`risk_adr` is refused.

**The render cap.** The grid caps at **60 rendered cards** with a client-side **`show N more`**
button appending the next 60. 60 is comfortably above every phase-1 population and only ever engages
against phase-2 `forming`. A labelled button, **not infinite scroll** — infinite scroll fights the
`IntersectionObserver` mini-chart loading and hides the total, where `show 156 more` keeps the count
honest.

**Reflow under the sheet — the opposite of the Board's choice.** There is no rail here; the ~540px
sheet docks against the grid directly. Freezing 3 columns would push the third under the sheet or
force a horizontal scrollbar, so **the grid reflows to 2 columns**, and **the clicked card stays
mounted with an active-state outline** so it survives the reflow and you do not lose your place.

### 5.3 Leaders

([#63](https://github.com/ajitimur/screening-dashboard/issues/63)) **One table with a lookback
segmented control — v1's five-up is retired** — and `k/5` is promoted from a badge you squint at to a
**sortable column**.

**Why the five-up loses on its own premise.** The claim was that five tables show persistence across
horizons at a glance, *which is what `k/5` means*. That is **false in the code**:
`ranks.breadth_counts` (`ranks.py:88`) counts the lookbacks a name is **top-decile** in, over the
whole rank table — *independent* of who makes any board's top 30. Top-decile is ~200 US names; the
board cuts at 30. So a name can read `4/5` while appearing on one board's top 30, and the glance and
the badge **actively disagree**. The badge is the honest number; the five-up is a redundant,
lower-resolution second encoding of it. Under the 1320px cap, five 5-column tables get ~264px each —
and the Board already owns the at-a-glance summary.

**Phase 1:**

- **One table, lookback = segmented control.** Default sort **return descending**. Sortable: return,
  `k/5`, ADR%, `$vol`. RS is P2.
- **Top 30 by return**, `(-raw_return, symbol)` tie-break exactly as `boards.py` does today.
- **Table / grid toggle ships P1** (a `radiogroup`, not an on/off). The grid is 3-up cards with lazy
  `MiniChart` via `/api/chart?bars=60` + `IntersectionObserver`. Both views share one row model, one
  sort, one filter set.

**Lookbacks.** P1 is v1's five under **v1's keys** — `1w / 1m / 3m / 6m / 12m`, not the reference's
`5d_thrust`; the contract, the store and `SURGE_THRESHOLD` all say `1w`. Only the display *labels*
adopt `1W / 1M / 3M / 6M / 12M`. **18M is P2**; **24M is out of scope**.

> **`k/5` is pinned to the original five by definition.** If 18M lands as a P2 column, it is a
> lookback you can *sort* by that does **not** count toward breadth — otherwise `breadth_counts`
> silently becomes `k/6` and every historical `4/5` changes meaning. The badge label stays `k/5`.

**Row furniture.**

- **`NEW` kept** — a badge on the ticker, scoped to the **active lookback** (`new_to_leaders`, not
  `new_tonight`; see [§2.4](#24-three-senses-of-new--two-survive-and-they-are-named-apart)).
- **Surge flag dropped.** `surge = 1w && return ≥ 30%` (`boards.py:112`) is redundant with the return
  column it rides — v1's own note records every surge name was already visible — and a 1w-only badge
  is awkward under a lookback switch. **The `1w` lookback *is* the thrust view.**

**Filters.** Ticker search + sector select + **"hide sub-4% ADR" toggle**, with ADR also a sortable
column.

- The toggle **survives** because this repo applies no universe-level ADR filter, so it is the
  **only liquidity floor this ungated universe has** — the work the reference's already-gated
  (≥4% ADR) universe does for free.
- **It defaults to ON** (sub-4% names hidden). This is a deliberate divergence from v1, which
  defaulted off. Consequence for the state matrix: a user can hit a zero-row table having **never
  touched a control**, so that empty must read as filter-inflicted
  ([§7.4](#74-empty-results-that-are-not-errors)).
- **Verdict filter is P2**, rendering `verdict: null` as *not evaluated*.

**Tier bands and the cutoff strip are the P2 additive layer.** P1 draws **no band column and no
cutoff strip** — a finished 30-row leaderboard, not a stubbed one. At P2 the band badge (1%/2%/3%)
and the cutoff-return summary become purely additive, and **the row count grows from top-30 to the
tier-banded top-3% population**, at which point "top 30" retires.

**Trailing summary line**, adapted from the reference:
`{n} names · ranked by {sort} · {market} · as of {session}` — with the honest count **after** the ADR
toggle and sector filter, so it reads as a live tally, not a fixed 30.

### 5.4 Sectors

([#64](https://github.com/ajitimur/screening-dashboard/issues/64)) **Stacked bands, not peer panels
side by side.** The decile table is too wide — 11 sectors × 5 lookbacks (`share` + `k/n`) + shape
differential + Δ20d — to sit beside a square RRG plot. The models stack, and RRG **appends above**.

**Phase 1 — two bands:**

1. **"Where the leaders are clustered"** — v1's `SectorTable` decile-share model at **full width**:
   five lookbacks with `k/n` fragility badges, shape differential, Δ20d, and the `k≥2` eligibility
   guard sinking thin sectors into a below-fold group.
   *Subtitle: share of the top momentum decile · five lookbacks.*
2. **Industry leadership board** (≥10 members), kept **market-wide** rather than pushed onto detail,
   so *"Semiconductors leads everything"* stays a top-level fact.

**Phase 2 — three bands**, RRG inserted **above**:

0. **"Where money is rotating"** — RRG plot + `QuadrantGuide` + a **slimmed companion list** (rank
   order / `rank_score` / trail arrow only; breadth columns shed because the decile band below owns
   that read).
   *Subtitle: pack return vs the peer composite · 3-week trail.*

**Both rotation models survive permanently.** They measure genuinely different things — pack return
versus breadth of decile membership — and the bottom-up read is not recoverable from the RRG. The
cost is accepted knowingly: **every future sector question has to be answered against two models.**

**One permanent disclaimer line sits between the two P2 bands**: the models disagreeing is
**breadth vs weight** — information, not error. It inoculates the reader before their first
contradiction.

**The pullback note survives, scoped.** Not redundant with the permanent regime band: the band says
*what the regime is*, the note says *what a CHOPPY/HOSTILE regime does to the meaning of decile
share* (relative strength through a decline cannot tell a mild pullback from a washout). One muted
line, attached to the **decile band only**, CHOPPY/HOSTILE only.

**The GECS caveat is a muted footnote on the RRG band** — its 3-week trail is exactly what makes a
silent relabel visible for the first time.

**Click-through.** Every sector-bearing mark is a real `<button>` into sector detail: decile-table
row, RRG point, RRG companion row, and industry row (→ its **parent sector's** detail).
**Ineligible/skipped sectors stay visible and still click through** — a thin sector is still a sector
you can open, so they are not empty states.

**The industry board is retained.** The reference's silence on industries is an absence, not a
decision; dropping a working ≥10-member leadership table to match it would be adoption eating
substance.

### 5.5 Sector detail

**Phase-1 columns:** `# · ticker · {lookback} return (bar + number) · pctile-in-lookback (population
named explicitly) · decile badge`.

**The decile badge is per the selected lookback and re-renders on switch** — not the reference's
single sticky `10%` chip, because this repo's decile is per-lookback (five) where the reference has
one. `ranks.py` writes a percentile per `(symbol, lookback, session)` today and `sectors.py:183`
already counts decile members off those rows, so **decile data is phase 1**.

**Lookback switch:** the five this repo ranks, default **1m** (matching the Board strip). The
reference's 18M/24M never arrive here.

**Toggles:** top-decile is **P1**; near-52w-high is **P2** (needs the absent 52-week high).

**P2, additive and nullable:** near-52w-high column + toggle, and the **verdict marker** — where
`null` on a pack member means *not evaluated*.

**Dropped from P1, not reserved:** ADR% and `$vol` — real pipeline cost for columns that do not drive
this page's question.

**Ticker** opens the one docked chart sheet.

**Back — two doors, both keyboard-reachable**, replacing the reference's floating `← Sectors` span:

1. A **`Sectors / Energy` breadcrumb** in the page header, `Sectors` a real `<button>`.
2. **Clicking the lit Sectors tab returns to the list** — spec'd explicitly, because a lit tab that
   no-ops is the drill-down's most likely bug.

The two exits behave **differently on purpose**: breadcrumb-back restores focus to the drilled row;
the tab gets the tab treatment ([§8.6](#86-focus)). Browser-back restores nothing
([§8.8](#88-history-navigation)).

### 5.6 Cross-screen navigation

**A carried filter is visible and dismissible at the destination** — a chip reading e.g.
`Sector: Energy ×`. It survives tab changes until dismissed or until the market changes.

| Jump | Destination | Carries |
|---|---|---|
| Board "view charts →" | Setups | `detected` verdict chip (a no-op at P1) |
| Board "See all →" | Leaders | nothing |
| Board sector bar / rotation map click | Sector detail | the sector |
| Sectors row / RRG point / companion row / industry row | Sector detail | the sector (industry → parent sector) |
| Sector detail breadcrumb | Sectors | nothing |

The reference's own expiry rule was **not** adopted: it clears filters on tab change *except*
Leaders, which keeps the sector. That asymmetry reads as accident rather than design, and a filter
that silently vanishes on a tab change is the same class of defect as one that silently persists.
**Making filter state a visible fact resolves both.**

---

## 6. The chart sheet

([#57](https://github.com/ajitimur/screening-dashboard/issues/57)) **One right-docked overlay sheet,
opened by click, identical on all four screens.** Neither source survives:

- **The reference's cursor popup** (372×178 chart, 620px pinned) is too small for what *this* repo's
  chart does. v2's chart carries strictly more overlay: shaded base with the cluster shaded inside
  it, the envelope drawn as a line the candles **pierce** (§3.2 — not corrected to a clean
  trendline), trigger and stop as horizontal rules, and the base's volume bars tinted so the dry-up
  dimension reads. At thumbnail size that is not evidence for a score. Cursor positioning compounds
  it — the pinned popup already clamps against the viewport before the breakdown is added.
- **v1's persistent panel** forces every screen to reserve ~40% width. The Board is `1fr + 384px` and
  cannot host a rail, so panel-only forces a per-screen split — two chart idioms in one app, exactly
  what the reference's IA got right by having one.

**Geometry:** right-edge, **`min(560px, 90vw)`**, full height, floating above the content with a
shadow. (`min()` rather than a fixed 560px because at 200% zoom on the 1280 target the effective
viewport is 640px, where a fixed sheet would cover ~87% of it.)

**Overlay, not squeeze.** Squeezing the content column reflows a 3-column grid to 2 on every open,
re-triggering every `IntersectionObserver` and re-laying-out every mini chart — paid on each click.
The overlay's one defect is that it can cover the card you just clicked; the fix is to **scroll the
selected row/card into the still-visible region on open**, not to reflow the page. (The Board instead
collapses its rail, and Setups instead reflows to 2 columns — both decided per-screen and both stated
above.)

### 6.1 Opening

**Click only. Hover does nothing — not even a prefetch.** The ticker becomes a real `<button>`, so
click, Enter, Space and tap are one door. Clicking a card's mini chart opens the same sheet.

Why hover dies rather than shrinking to a prefetch:

- A 540px full-height sheet flapping open on mouse movement is violent in a way a 372px popup is not.
- **Cheap in the reference, expensive here**: `/api/chart/{market}/{symbol}` recomputes the session's
  rank table per call (`app.py:250-269`). Sweeping a 50-row Leaders table would be 50 rank-table
  recomputes for charts nobody opened.
- Its value is already on the page — mini charts give the at-a-glance shape without summoning
  anything.

### 6.2 Lifecycle

- **Exactly one sheet, ever.** Side-by-side comparison is the grid's job.
- **Clicking a different ticker swaps the sheet's content in place**, no close-and-reopen. This is
  v1's genuinely best property — click down a list and watch one surface change — and it is
  preserved.
- **No backdrop.** The page stays interactive behind the sheet; that is what makes click-down-the-list
  work at all.
- **Non-modal, no focus trap.**
- **Closes on**: Esc · the × · clicking the same ticker again (toggle) · a tab change · a market
  switch. Back **navigates** and the sheet closes as a side effect of the first two of those
  ([§3.5](#35-url-and-history)).
- **The source row or card stays visibly lit** while its sheet is open.

### 6.3 Content — one form, no reduced variant

Top to bottom:

1. **Header** — symbol · verdict badge (neutral, no colour) · sector · ×
2. **Chart** — candles (unadjusted), SMA 10/20/50 + EMA 65 with the MA legend, volume histogram, and
   the full setup overlay: shaded base, cluster shaded inside it, pierced envelope, trigger and stop
   rules, base volume tinted
3. **Facts block** — trigger, stop width ×ADR, distance ×ADR, ADR%, base length, dollar volume,
   decile rank per lookback
4. **The eight-row §4.7 breakdown, last** — each dimension, its weight, whether it scored, and the
   `n/10 → stars` arithmetic

**The breakdown goes last, not adjacent.** v1 set it beside the chart because it had horizontal room;
a ~540px column does not, and the breakdown is audit material you consult *after* reading the chart.
It renders from the **candidate row's** `breakdown` field, so **it paints while the candles are still
in flight**.

**Degraded state** — a name with bars but no detection tonight: the chart draws; overlay, facts and
breakdown are replaced by one explicit line saying there is no base tonight. v1 already behaves this
way and it is kept.

### 6.4 Mini charts

Kept **exactly where the reference has them, and nowhere else**: **Setups cards** (always) and
**Leaders' grid view**. Board hero cards and the sector-detail table stay chart-less.

Inline lazy `MiniChart` — `IntersectionObserver` with a 200px `rootMargin`, `/api/chart?bars=60`,
payload shared with the sheet through one frontend cache keyed `(market, symbol, bars)`.

Without them, Setups shows trigger and stop numbers but no shape, and the only way to see 27 shapes
is 27 sheet-opens one at a time. They are also what made killing hover-open cheap.

**Phase 1 accepts the N+1 on call count** — cache plus `IntersectionObserver` makes it tolerable, and
it is the same bet the reference makes. What it does **not** accept is shipping full price histories
for 60-bar thumbnails, which is what `?bars=` exists for.

---

## 7. Empty, loading, error and stale

([#65](https://github.com/ajitimur/screening-dashboard/issues/65))

### 7.1 The seam

**One seam, cut by what a read *means* — not by which component issued it.**

- **Shell-owned (identity): `/api/runs` and `/api/regime`.** These answer *what night is this*. If
  either fails, **no screen may render** — you cannot honestly draw a Board whose header cannot say
  its own session. **One** alert, in the tab body's place, and that is **the only `role="alert"` the
  app is allowed to raise**.
- **Panel-owned (body): the other seven.** A dead `/api/sector-rrg/{market}` collapses the Board's
  rotation panel to a one-line notice; hero cards, leaders strip and funnel line stay live. N panels
  may fail, producing N notices — and **a panel notice is deliberately not `role="alert"`**, so three
  dead panels do not shout three times.

v1 has no seam at all: `App.tsx:126` blanks the entire app on one failed `/api/runs`, while
`CandidateList.tsx:52`, `SectorTable.tsx:92`, `Boards.tsx:46` and `ChartPanel.tsx:90` each throw an
independent `role="alert"` below it.

This also closes a v1 silence: `App.tsx:119` is `.catch(() => {})`, so a dead `/api/regime` today
makes the §4.9 band simply **not exist, unannounced**. Making the band permanent chrome is exactly
why regime is classed as identity rather than as a body read that may quietly vanish.

### 7.2 No run yet

**The shell owns `session: null` exclusively. A screen is never mounted with a null session.** One
statement, once, replacing the whole tab body.

This kills v1's duplication, where `App.tsx:147` and `Boards.tsx:48` answer the same question
separately and in disagreeing prose. **Cost accepted in the open**: on a night where IDX has
published and US has not, flipping the market control swaps the entire tab body for a sentence. That
is the true fact, and four screens each improvising their own wording for it is how v1 ended up with
two.

### 7.3 Loading

**Same seam, progressive paint.** The shell blocks on the identity read only; after that each panel
loads itself and paints when ready. The Board's hero cards land before the leaders strip.

**No whole-screen skeleton gated on every read** — that makes the Board hostage to its slowest panel
for no honesty gain. The chart sheet already commits to this idiom internally, where the breakdown
paints before the candles.

### 7.4 Empty results that are not errors

**Two registers, divided by one rule:**

> **If the user can make it non-empty by clicking something on screen, the empty state must contain
> that click.**

- **Night-inflicted** — IDX `forming` holding two names, a sector with no member rows, an industry
  board under the ≥10 guard. These are **facts**, stated in the panel's own frame, in body copy,
  **naming the number**. **Prose that never apologises**: five detected names is a *finished* screen,
  not a degraded one.
  **Wording is transcribed from v1, not reinvented**: `CandidateList.tsx:63` — *"No candidates
  tonight — no name is sitting in a valid base"* — is the model, and `SectorTable.tsx:179` already
  carries the right prose for the industry guard.
- **Filter-inflicted** — a ticker query matching nothing, a carried sector chip, the default-ON
  sub-4% ADR toggle hiding every row. These are **recoverable**, so they carry the escape hatch
  inline: **the offending chip and a clear-filter action**.

**Neither register uses the error treatment.** The ADR toggle is the sharpest case: a user can hit a
zero-row Leaders table having never touched a control, and that empty is still filter-inflicted and
must say so, or the divergence from v1 reads as a broken screen.

### 7.5 Phase-2 panels — there is no "not yet" state

**Dissolved, not decided.** Every P1 shape is drawn complete-in-itself and every P2 field is purely
additive ([§1.4](#14-the-phase-1--phase-2-boundary)); every degraded panel has a substitute that
actually renders — the decile table for the RRG, the top-5 sector bars for the rotation map, `k/5`
for the tier bands, v1's five lookbacks for 18M. **No panel was found that fails the test.**

**No general escape hatch is left open, deliberately** — one would reintroduce `PHASE 1` badges
through the back door.

### 7.6 The mid-flight market switch

**Blank the values, keep the frame.** Panel-shaped skeletons at the panel's **real dimensions**,
`aria-busy` on the containers, **static — never shimmering**.

Two failure modes rejected:

- **Showing IDX numbers under a `US` label**, even dimmed for 200ms — the one state here that could
  produce a wrong trade.
- **Collapsing the layout**, which reflows the Board twice per switch.

v1's `setData(null)` → `Loading candidates…` text node (`CandidateList.tsx:42`, `Boards.tsx:36`,
`SectorTable.tsx:68`) does both, and got away with it because market was buried behind a tab.
Promoting market to a header segmented control makes this **the most-pressed control in the app**,
turning a rare flash into a constant one. **This is the one place added complexity is accepted.**

### 7.7 The chart surfaces

- **Sheet: full treatment, never blocked on the canvas.** Header, facts and the breakdown paint
  immediately; the chart area skeletons. A failed chart read replaces the canvas only — the breakdown
  stays readable.
- **Mini charts: silent.** A failed or slow mini chart is an empty frame — no message, no notice, no
  alert. At 60 cards, per-instance error text is 60 apologies; the card's numbers are load-bearing and
  the chart is confirmation, so a card whose mini chart never arrives is still fully usable.
  **This is the one exemption from the panel-notice rule, and it is granted on volume.**

---

## 8. Accessibility

([#66](https://github.com/ajitimur/screening-dashboard/issues/66),
[#67](https://github.com/ajitimur/screening-dashboard/issues/67),
[#69](https://github.com/ajitimur/screening-dashboard/issues/69))

### 8.1 Conformance statement

> **v2 conforms to WCAG 2.1 Level AA, with exactly one carve-out: SC 1.4.10 (Reflow).**

A single named, auditable hole rather than a bespoke self-graded checklist.

- **SC 1.4.10 Reflow is not met, by decision.** v2 is desktop-only at ≥1280 with bare horizontal
  overflow below ([§1.3](#13-standing-constraints)). The blunt-sentence floor wall was considered and
  declined: for an audience of one it buys presentability no one sees, at the cost of a `min-width`
  wall that would lock a zooming low-vision user **out** rather than let them scroll. Bare overflow
  is cheaper *and* less hostile.
- **SC 1.4.4 Resize text *is* claimed.** 1.4.4 permits two-dimensional scrolling; only 1.4.10 forbids
  it — so v2 can fail Reflow and pass Resize. This matters because with no reflow and no wall,
  **zoom-to-enlarge is the only low-vision accommodation v2 offers**, and 1.4.4 is the sole thing
  standing under the 9.5px density bet. It has teeth: `min()` sizing, `min-height` over `height`, and
  **no `overflow: hidden` on text containers** ([§3.2](#32-tokens)).
- **Not WCAG 2.2.** 2.2 adds SC 2.5.8 Target Size (24×24 CSS px), which the 9.5px dismissible filter
  chips fail head-on. That is a *second* collision with the density, and this effort has spent its
  one exemption.
- `<html lang="en">` is already present; SC 3.1.1 discharges itself.

### 8.2 The claim in one line

The density bet is **defended by darkening the palette, not by inflating the scale.** The type scale
is untouched. **9.5px is never "large text" under any WCAG version**, so the 4.5:1 line applies flat
and no size argument rescues it — contrast is the whole game.

### 8.3 Contrast — the measurement that decided the palette

The reference's `theme.ts` as adopted:

| Foreground | on `card #fff` | on `surface #f6f4ef` | on `bg #e7e4de` |
|---|---|---|---|
| `text #1c1b18` | 17.22 | 15.67 | 13.57 |
| **`textMuted #8a857c`** | **3.67** | **3.34** | **2.89** |
| **`textFaint #a09a8e`** | **2.80** | **2.54** | **2.20** |
| `green #1f8a4c` | 4.38 | 3.98 | 3.45 |
| **`amber #c08a2e`** | **3.04** | **2.76** | **2.39** |
| `red #c8492f` | 4.72 | 4.29 | 3.72 |
| **`underline #b3ab9d`** | **2.28** | **2.07** | **1.79** |

`textMuted` is `statLabel`'s colour — **every 9.5px label in the app** — and it fails AA on every
surface, failing even the 3:1 large-text line on `bg`.

**The changes**, already reflected in [§3.2](#32-tokens):

- **`textMuted` → `#6b665c`** (4.50 on the worst background, 5.71 on card).
- **`textFaint` dies as a text token.** It was never decoration: it carried table column headers
  (`BoardView.tsx:100`, `SectorDetailView.tsx:120`), row numbers, footnotes, the `–` null marker
  (`LeadersView.tsx:22`), and **most of the empty and loading copy**. Three neutral steps that all
  clear 4.5:1 on paper are three greys nobody can distinguish — the bottom rung existed *because* it
  was too light. It survives as a **non-text fill only** (regime `unknown` dot, negative bar, sector
  fallback), where 1.4.11's 3:1 applies and `#a09a8e` still fails at 2.20 on `bg`, so **even there it
  needs a lift**.
- **Semantic trio darkens for text use**: `green #17703e` (5.58), `amber #8a6215` (4.98),
  `red #b03d26` (5.39) on surface.
- **`underline` splits in two.** At 2.07 it was the app's worst failure and it did two jobs: real
  text (rank numbers, RRG axis labels) and the ticker's `1.5px dotted` affordance. **Text uses take
  `textMuted`; the affordance becomes its own token at a 3:1 floor.**
  **The dotted underline is kept**, even though the ticker is now a real `<button>` — dropping it
  leaves the ticker with **no persistent affordance**, since the focus ring is keyboard-only and hover
  is pointer-only, and on a grid of up to 60 cards *"which of these is clickable"* would be
  answerable only by probing.

**Also load-bearing**: the reference has **zero** `focus`, `aria-`, `role=` or `tabIndex` across
`web/src/` against 44 `onClick` handlers. **Every semantic below is invented, not ported.**

### 8.4 Colour that carries meaning

- **As text (1.4.3)**: the semantic trio darkens as above.
- **As non-text (1.4.11, 3:1)**: **sector swatches are exempt where the sector is named in adjacent
  text** — the decile table and the Board's rotation bars — so the hue is wayfinding convenience, not
  carrier. **The exemption dies where a swatch appears without its name**: the P2 **RRG plot**
  inherits the 3:1 floor on its dots.
- **1.4.1 Use of Color**: the Board's rotation bars encode sign by hue alone in the reference
  (`score >= 0 ? sectorColor : textFaint`), with no sign in text and no shape difference. They become
  **centre-anchored diverging bars** — left negative, right positive. Rotation is directional, so a
  bar growing away from a centre says what the panel is named for, where a one-sided two-colour bar
  makes the reader learn a legend. It also keeps sector hue meaning-free, preserving the exemption
  above.

### 8.5 Semantics and roles

| Surface | Role |
|---|---|
| Tab row | **`role="tablist"`** — roving tabindex, arrows move, Tab escapes, panels associated |
| Market control | **`radiogroup`, not tabs** — a market switch *resets entity state and refetches*, it does not reveal a sibling panel. Calling it a tablist promises a `tabpanel` that does not exist |
| Leaders' table/grid toggle | **`radiogroup`** — two peer views of one dataset, not an on/off |
| Sector detail | **navigation** — the breadcrumb is the honest control |
| Leaders' table | **a real `<table>`** with `<th scope="col">`, a `<button>` inside each sortable header, and **`aria-sort` on the `<th>`** |
| Cards (hero, Setups, Leaders grid) | **`<article>`** named by ticker, stats as **`<dl>`/`<dt>`/`<dd>`** |

**The `<table>` matters**: the reference's grid-of-`div`s is the largest semantic regression on offer
— 30 rows × 7 columns of `div`s gives no column context on any cell — and Leaders is *the deep
table*. `aria-sort` matters because sorting is its primary interaction.

**The `<dl>` patches a hole in the testing mechanism.** `statLabel` + `statMono` are sibling `<span>`s,
so a screen reader reads `"TRIGGER" "12.45" "STOP" "11.80" "DIST" "0.8"` as six unrelated strings —
and a role/name query contract is **silent** on this, because a `<span>` has no queryable role.
`<article>` also makes cards queryable by role without a `data-testid`, feeding the mechanism rather
than bypassing it. **Rejected**: per-stat `aria-label` merging label and value — it duplicates every
number into an attribute that drifts from the rendered value, across 60 cards.

**Bypass and structure** (SC 2.4.1, level A): landmarks (`banner` / `nav` / `main`) **plus** a
visually-hidden **skip link** that appears on focus — landmarks alone serve screen-reader users and
do nothing for a sighted keyboard user. Plus **per-panel `<h2>`s that are programmatically the
panel's name**, which is free: panels are already named for their behaviour
("Where money is rotating", "Where the leaders are clustered"), so making those names headings turns
the naming rule into the navigation structure.

**`document.title` updates per screen** (`Board · US · Screening Dashboard`) for SC 2.4.2, level A.
It **keys off the same in-memory destination values whether or not the URL carries them, so 2.4.2 is
discharged independently of the routing decision.** It does real work: with two markets and identical
screens, the title is the only persistent statement of which market is on screen outside the
segmented control.
**Stated non-role: `document.title` is *not* an announcement mechanism.** Screen-reader handling of
title changes on same-document navigation is inconsistent, so it can never be recruited to discharge
the announcement obligation of [§8.8](#88-history-navigation).

### 8.6 Focus

**One two-tone `:focus-visible` ring token** — dark core + light halo, readable on any background.
The forcing case is the market control and the tab row: `segItem` puts the *active* item as light
text on `#1c1b18`, so a single dark ring vanishes on the most-pressed control in the app. Two-tone is
one token to specify and test, and survives the chart sheet overlapping the Board.

**`:focus-visible` only, never `:focus`** — mouse clicks on 60 ticker buttons and the breadcrumb must
not scatter rings across a dense board.

**One focus-management rule, everywhere:**

> **Activate a thing and focus lands in the thing. Leave it and focus returns to where you were.**

- **The chart sheet** is portalled at the end of the DOM; focus moves to the sheet's `<h2>`
  (`tabIndex={-1}`) on open and **returns to the trigger on Esc/close**. This dissolves the SC 2.4.3
  Focus Order problem rather than arguing it — *"I clicked a thing, my focus is in the thing"* is the
  least surprising sequence available. **Tab from the sheet's last element continues into the page
  behind it rather than cycling — that is intended**, and is what "non-modal, no trap" bought.
  Rejected: injecting the sheet after its trigger in the DOM (visual/DOM divergence), and portalling
  *without* moving focus (unusable at 60 cards).
- **A content swap re-runs the open behaviour**, moving focus back to the heading — otherwise a swap
  detaches the node focus is sitting on. This makes clicking a second ticker and clicking the first
  behave identically, which is what *"one sheet ever, content swapped in place"* was reaching for.
- **The sector drill-down** moves focus to the detail page's heading; **breadcrumb-back restores
  focus to the row that was drilled into** — which matters because the industry board is market-wide,
  so that is a long list to re-find. The *other* exit, the lit Sectors tab, gets the tab treatment
  instead. **The two exits behaving differently is correct.**

### 8.7 Sound: one alert, three polite regions

The count of three **is itself the decision** — recorded so the next person adding a live region must
justify it against a number.

| Region | Assertiveness | Fires on |
|---|---|---|
| Identity-read failure | **`role="alert"`** — the app's only one | `/api/runs` or `/api/regime` failing |
| Panel failure notices | `role="status"` | any body read failing |
| The chart sheet's heading | `aria-live="polite"` | open, and every content swap |
| **Destination change** | polite | **`popstate` only** — see [§8.8](#88-history-navigation) |

*(The third and fourth rows are the second and third polite regions; the alert is not one of the
three.)*

- Panel notices are polite because the rule was *"don't shout three times"*, not *"don't speak"* —
  polite regions queue rather than interrupt.
- The sheet's heading region exists because a **silent full-content swap is louder than anything
  classed as a notice**.
- **`aria-busy`** on skeleton containers.

**Motion (house rule, outside the claim** — SC 2.3.3 is AAA**)**: a blanket
`@media (prefers-reduced-motion: reduce)` zeroing every transition, applied globally rather than per
component. **Skeletons are static, not shimmering** — a shimmer across four Board panels at once
during a market switch is the most motion-heavy moment in the app, produced by the most-pressed
control.

### 8.8 History navigation

([#69](https://github.com/ajitimur/screening-dashboard/issues/69))

> **A history navigation moves no focus and announces its destination.**

**Focus: nothing moves.** Not the destination's `<h2>` (that is the drill-down treatment applied to a
tab change, where a click leaves focus on the tab button per the ARIA tabs pattern — back and click
would then diverge for the same destination). Not the control that names the destination. Not a
conditional move-only-if-orphaned rule, which would make behaviour depend on where the user happened
to be standing and is untestable as a contract.

**The accepted cost, stated rather than discovered:** when a back unmounts the node focus was sitting
on, focus falls to `<body>` and the next Tab restarts at the top of the document. **The skip link is
what makes this survivable**, and it is already shipping for SC 2.4.1.

**Two consequences neither parent decision listed:**

1. **The sector detail's two exits diverge on purpose.** Breadcrumb-back restores the drilled row;
   browser-back to the same list restores nothing. **The asymmetry is the rule working** — it tracks
   whether a control was pressed. Collapsing them would delete a restore justified on a concrete
   cost.
2. **Back with the chart sheet open fires no focus-return.** A navigation-induced close is a
   **teardown, not a close**; focus-return was given to Esc and to ×, both user acts. The alternative
   makes focus behaviour depend on whether a DOM node outlived a navigation, and can throw focus back
   into a screen the user has just navigated away from.

**Announcement is therefore the only signal a history navigation has.** The market-switch *eject*
region is **generalised** rather than joined by a fourth: its real subject was never "market switch",
it was *your destination changed and no click of yours put you there* — which is exactly what back
does.

- **`popstate` only, never pushes.** Clicking a tab or a market already announces through the
  control's own role, name and state; firing on pushes would double-speak the most common action in
  the app.
- **Forward is identical to back.**
- **It announces the destination on the three URL axes and only those** — `"Leaders, US"`, and on the
  drill-down `"Energy, Sectors, IDX"`. **Never the mechanism**: *"went back to…"* tells the user the
  one thing they already know.
- The region is **named for its behaviour**, not its original trigger.

**The silent fallback stays fully silent.** An unhonourable URL resolves and rewrites via `replace`
with no error, no alert, and **no announcement of the correction** — not on cold load and not later.
The `replace` is load-bearing precisely so **no dead destination survives to be replayed**, so a back
or forward always lands on a real destination and announces *that*. A notice would be the app
apologising for something the user's own URL got wrong, in a one-user app.

### 8.9 Graphics: colour is never the carrier

SC 1.1.1 is level A, and the two chart surfaces differ in kind — `lightweight-charts` is **canvas**
(opaque), the RRG is **SVG** (`viewBox="0 0 100 100"`, every node addressable).

- **`aria-hidden` where adjacent text already carries the data.** The sheet states trigger, stop,
  distance and the breakdown as text, so a generated *"candlestick chart of ABCD, 60 bars"* label
  adds nothing and **lies by implying the chart is summarisable**. Mini charts are decorative — every
  card states its numbers above them, consistent with them already being silent on failure.
- **The RRG's text alternative is the sector companion list**, which exists for sighted reasons and
  discharges 1.1.1 exactly. The SVG is `aria-hidden`.
- **Per-dot `<title>` elements are rejected** — they invite navigating a quadrant scatter by tab
  order, where **position is the meaning** and tab order destroys it.
- **The consequence worth recording: the accessible path to sector rotation is the decile table,
  always** — which is also why the RRG is P2 and the table is P1.

### 8.10 Enforcement, and what it honestly cannot catch

**`vitest-axe` in each screen-level suite.** One devDependency, one line per suite, in the harness
already chosen — and the natural extension of *a component with no accessible name is untestable, so
it cannot ship*. It catches missing names, bad roles, orphaned controls and heading order.

`eslint-plugin-jsx-a11y` is not "add a plugin", it is "stand up a linter from zero"
(`frontend/package.json` has no ESLint config, no plugin, no `lint` script) — ruled out of scope.

> **⚠ The caveat is part of the decision.** jsdom has no layout and no computed colour, so **axe
> verifies none of the contrast work and none of the focus ring.** Those are verified **once, at the
> token level**, by a human against the ratio table in [§8.3](#83-contrast--the-measurement-that-decided-the-palette),
> using the idiom this effort established: **screenshots of a built artifact, reviewed by a human.**
> Contrast is checked per *token*, not per screen. **The contrast decisions in this spec have no
> automated guard.**

---

## 9. Testing

([#60](https://github.com/ajitimur/screening-dashboard/issues/60))

### 9.1 The query contract

**Assert through role + accessible name** (`getByRole`, `getByLabelText`), as v1 does.
**`data-testid` is allowed only as a documented escape hatch** for surfaces that genuinely have no
role: the `lightweight-charts` canvas and the sector RRG plot. **No blanket test-id regime.**

This makes the query contract an **enforcement mechanism, not a style**:

> **A component with no accessible name is untestable, so it cannot ship.**

That polices *semantics* — landmarks, roles, names, `aria-current`, focus order — exactly the surface
the adopted IA raises the stakes on.

**Ownership split** (and the same split governs [§8](#8-accessibility)): **this section sets the
mechanism; the accessibility section sets the standard** (WCAG level, contrast, focus visibility,
zoom behaviour). Role queries assert semantics, never type size, so **nothing here reopens the 9.5px
density bet** — a 9.5px label with a correct accessible name passes untouched.

### 9.2 The harness

**Keep `vi.stubGlobal("fetch", …)`. Do not adopt MSW.** The ~1,100 v1 lines are **fixture plumbing,
not routing** — MSW would pay a dependency and a setup file to fix the smaller half.

**Collapse the per-file hand-rolled route maps into one shared typed fixture module built off
`schema.d.ts`**, so the nine-endpoint contract and its P2-nullable fields are constructed once, typed,
and reused.

The MSW refusal was tested twice and survived both:

- Asserting the market-switch skeletons needs **in-flight control, not request interception** — a
  deferred promise through `vi.stubGlobal(fetch)` supplies it.
- The URL contract needs `history` and `popstate`, both of which jsdom implements.

### 9.3 Coverage shape

**Screen-level suites, not per-component.** The screen is the unit of IA, and components are now
shared across screens — per-component suites would duplicate fixture plumbing exactly the way v1's
five files already do.

| Suite | Covers |
|---|---|
| **Shell** | header, as-of, permanent regime band, conditional run-status banner, market segmented control, tab navigation, run-on-open lifecycle, **the URL contract**, **the `popstate` announcement** |
| **Board** | |
| **Leaders** | |
| **Setups** | |
| **Sectors** | including sector detail |
| **Chart sheet** | one dedicated suite — the sheet is a single object appearing identically on all four screens and swapping content in place, so it is tested **once as itself** rather than re-tested inside every screen |

Two cases the shell suite must name explicitly:

1. **Back after a market switch restores the whole prior destination** — the one a future reader is
   most likely to "fix" into a bug.
2. Each of the four unhonourable URLs falling back **and rewriting**.

Plus **one assertion and one recorded refusal** on history navigation: assert that a `popstate`
produces the destination region's text; **deliberately assert nothing about focus** — recorded as a
decision, not left as an untested area, so a later reader does not "fix" the gap by adding the focus
management [§8.8](#88-history-navigation) refused.

### 9.4 Untestable by design

**Charts are asserted at the library seam only** — the data handed to `setData`, the overlay price
lines requested of the series (base/cluster bands, envelope, trigger/stop rules) — **never as
pixels**, via `vi.mock("lightweight-charts")` as v1 already does. The RRG plot is asserted the same
way.

**No browser / visual-regression tier**, ruled out of scope. Uncovered by construction, and named
plainly so an implementing agent is not surprised:

- visual layout and the full-bleed / 1320px-cap frame
- the token set actually rendering colour
- the right rail collapsing while the chart sheet is open
- contrast ratios and the focus ring ([§8.10](#810-enforcement-and-what-it-honestly-cannot-catch))
- anything requiring the real backend

**Human-reviewed screenshots of a built artifact** are this effort's idiom for exactly those
surfaces.

### 9.5 The interim rule

> **A v1 test file is deleted in the same commit as the v1 component it covers — never earlier.**
> No wholesale up-front deletion, no window of red tests.

The behaviour checklist in [Appendix A](#appendix-a--the-behaviour-checklist) exists so those
behaviours survive as prose during any window where no test file holds them.

---

## 10. Migration and rollout

([#71](https://github.com/ajitimur/screening-dashboard/issues/71))

**Big-bang on a branch, merged once — but the backend goes first and lands on `main` alone, so the
branch is a frontend-only diff.**

### 10.1 Why big-bang, when it is usually the wrong answer

Two facts about *this* repo, not preferences:

- **v1's frontend is 1,021 lines of component code** across five files (`App.tsx` 229,
  `ChartPanel.tsx` 329, `SectorTable.tsx` 212, `Boards.tsx` 132, `CandidateList.tsx` 119). **The
  rewrite is smaller than the machinery built to avoid it.**
- **There is no deploy pipeline and no environments.** A flag de-risks exposing a change to users you
  cannot ask; there is one user, at one desk, who can be asked. Standing up a flag mechanism means
  building the thing that does not exist in order to protect a production that does not exist.

**Incremental is refused on a structural fact, not on effort**: the shell, the Tailwind setup and the
URL state underlie all four tabs, so a shared floor must exist before any single screen can ship.
Screen-by-screen therefore means either v2's shell wrapped around v1's screens or v1's shell around
v2's — **a hybrid that has to be built, debugged and then thrown away, and that no ticket spec'd.**

### 10.2 The three ordering constraints

The spec carries these and stops:

1. **Backend growth lands first, on `main`, with `/api/boards` aliased for the branch's lifetime.**
   The growth is additive except the rename, so `main` is never not-runnable and v1 keeps running
   throughout.
2. **No window of red** — [§9.5](#95-the-interim-rule)'s rule, transcribed.
3. **v1's five components, their five test files, and the alias die in one commit**; `openapi.json`
   and `schema.d.ts` regenerate in that commit.

**Why backend-first is load-bearing and not just tidy**: `dump_openapi.py` → `gen:types` →
`schema.d.ts` runs on `main`, so **the real v2 contract is typed before a single v2 component is
written** — and the one-typed-fixture-module collapse of [§9.2](#92-the-harness) has nothing to
generate from otherwise. The v2 branch is then a pure frontend diff against a contract that already
exists, rather than one branch carrying two half-built halves that cannot be tested against each
other.

### 10.3 Two seams ported, all markup rewritten

Not two components — two **seams**, the parts encoding behaviour rather than shape:

- **`ChartPanel.tsx`'s `lightweight-charts` setup.** The only integration of that library in the
  repo, needed by both the docked sheet and the mini-chart grid, and the exact seam the tests assert
  at *because* it already exists.
- **`SectorTable.tsx`'s eligibility guard.** Sectors' phase-1 band is "v1's full-width decile-share
  table, eligibility guard and all" — the guard is hard-won logic, not layout.

**Everything else is written from zero.** Markup is precisely where Tailwind, the card and table
anatomy, and the semantics of [§8](#8-accessibility) all land — so porting markup would import v1's
shape into screens whose shape this map spent eleven tickets respecifying.

### 10.4 What the spec does not carry

**No build plan.** The precedent is that the spec reaches into sequencing only where there is a
correctness reason — the three constraints above have one; a ticket-by-ticket ordering does not, and
would be stale before it was read. **The unit of delivery below those constraints is the
implementation effort's call.**

---

## 11. Known defects and open risks

### 11.1 The ≥3.5★ cut is load-bearing on an unvalidated rubric

**⚠** The Board's hero cut makes a rubric cut load-bearing, which §4.7 says reopens the rubric's
validation. **Accepted cold**; recalibration is out of scope.

The cost, stated plainly: §4.7 publishes measured behaviour at the **4★** line (precision 0.53,
recall 0.28, fires on 18.3% where the eye grades 35.2%). **3.5★ has no published behaviour at all.**
4★ was chosen first and abandoned when the measurement showed it yields **0 cards on IDX and 1 on
US** — an empty screen. 3.5★ yields 3 and 8.

**Board membership also replays.** It is derived from a score that is never stored, so **a corrected
rubric silently rewrites Board history.** The verdict does not — it is detector-sourced and stable.

### 11.2 The population measurement bounds what can be trusted

| Market | Universe | Entering detection | `detected` | near-miss |
|---|---|---|---|---|
| IDX | 80 | 14 | 5 | 9 |
| US | 1167 | 246 | 27 | 216 |

Stable across three sessions. **100% of IDX and 99% of US rejections inside detection are immature**,
which is what makes `rejected` a counter rather than a table.

**⚠** The US universe was reconstructed mid-run and is NASDAQ-skewed (78% of NYSE/AMEX candidates had
no bars — an interrupted ingest), so **trust US ratios, not levels**; true counts are plausibly
1.5–2× higher. The histogram counts first-rejection only — *"failed ≥1 immature test"* is 216 where
*"failed exactly one"* is 97, **a 2× spread in what `forming` would actually hold.**

### 11.3 Phase-2 costs, surfaced rather than deferred

- **Verdict persistence is ~8× the detection rows on US** — the single largest P2 pipeline change.
- **The RRG is the one computation filed as expensive** — a `dates × members` matrix, EWM, a per-date
  cross-section, plus a second whole-universe pass, retaining a 3-week trail.
- **24M does not fit the rank table's 2-year retention** and is out of scope.

### 11.4 Two rotation models, permanently

Every future sector question now has to be answered against two models that measure different things.
The disclaimer line and the behaviour-naming of the panels are the mitigations; the cost was accepted
knowingly.

### 11.5 The taxonomy will rewrite history silently

**⚠** GECS labels carry a single `as_of` and no effective period. A relabel silently rewrites history,
and the P2 RRG's 3-week trail is what will make it visible for the first time. Fixing it is out of
scope; the contract records `taxonomy: "GECS"` so the fact is at least legible.

### 11.6 The density bet has one accommodation and no automated guard

**⚠** 9.5px labels are at the legibility floor. With no reflow and no floor wall,
**zoom-to-enlarge is the only low-vision accommodation, and it yields horizontal scroll.** SC 1.4.4's
`min()` sizing is the sole thing standing under it. And per
[§8.10](#810-enforcement-and-what-it-honestly-cannot-catch), **the contrast work and the focus ring
have no automated guard** — they are verified once, at token level, by a human.

### 11.7 The empty-file convention stops being an alerting mechanism

v1's *"a missing digest file unambiguously means the run failed — that is the whole of v1's
run-failure alerting"* is **superseded**: `/api/runs` is now an identity read gating every screen and
holding the app's single alert, and the run-status banner is permanent chrome. The empty-file
convention stays in the pipeline because it costs nothing and an empty file is honest, **but it is no
longer an alerting mechanism** — a second, independent failure signal nobody watches is worse than
none.

---

## 12. The amendment chain

Later tickets amended earlier ones. **This spec carries the current answer only**; this table exists
so nobody re-derives a superseded decision from an old thread.

| Amended | By | The change |
|---|---|---|
| #54's *"pipeline growth, not endpoint growth"* | #56 | **Wrong for the setup card** — `trigger`, `stop`, `sector`, `adr`, `dollar_volume`, `decile_ranks` all exist today inside `/api/chart`. That is plain **endpoint** growth |
| #55's CSS-variable escape hatch | #59 | Still right, but **incomplete**: Tailwind v4 tree-shakes `@theme` vars no utility mentions, so a runtime-only token set needs `@source inline(...)` or a plain `:root` — and **the failure is silent** |
| #53's `>3.5★` | #61 | **`≥3.5★`** — on half-star granularity `>3.5` means 4.0+, collapsing IDX to one card |
| #56's *"two peer panels"* on Sectors | #64 | Physically impossible — the decile table is too wide beside a square plot. **Stacked bands**, RRG appending above |
| #56's *"per-name decile is P2"* | #64 | **Decile is P1** — `ranks.py` writes it today. Only `pct_of_52w_high` is P2 |
| #58's `LeaderRow` | #63 | **Adds `sector` and `dollar_volume` as P1 fields**, so the control bar ships whole instead of with two dead controls |
| #58's open `?verdict=` question | #62 | **Discharged: no param needed.** A client-side 60-card cap fixes the only real cost (rendering 216 mini-charts); the JSON was always cheap |
| #59's *"palette adopted wholesale"* | #67 | **No longer wholesale** — neutral ramp collapses to two steps, `textFaint` dies as a text token, semantic trio darkens, `underline` splits |
| #59's px grid | #67 | **Design-target values under `min()`**, `min-height` over `height`, `overflow: hidden` banned on text containers |
| #57's sheet at ~520–560px | #67 | **`min(560px, 90vw)`** |
| #67's `document.title` premise (*"needs none of the routing #64 fogged"*) | #69 | **Premise stale** — the routing exists. **Conclusion unaffected**: the title keys off in-memory destination values either way. Plus a stated non-role — the title is **not** an announcement mechanism |
| #67's third polite region (market-switch eject) | #69 | **Widened to every `popstate`**, so the closed set stays at three |
| #57's *"hoist the per-session rank recompute"* | #57 itself | Dropped to a **nice-to-have** when hover-open died; it was only load-bearing to make prefetch defensible |

---

## Appendix A — the behaviour checklist

v1 behaviours that **survive**, ported to the new markup and asserted by role/name. This list doubles
as prose insurance during any window where no test file holds them
([§9.5](#95-the-interim-rule)).

**Shell / lifecycle**

- [ ] Run-on-open kick when the last final session is missing, its progress `status`, and the
      poll-to-published transition
- [ ] Quarantined-latest banner while still serving the last good session
- [ ] No-run-yet empty state, kept **distinct** from a run-**failed** alert
- [ ] Regime banner's four states, including "warming up / no posture" and the no-banner-before-first-run case
- [ ] **Market switch resets entity-naming state (symbol, sector, query) and keeps shape state (tab,
      lookback, sort, verdict filter)** — v1's "clears selection" test, **ported with new
      expectations, not dropped**
- [ ] Back after a market switch restores the whole prior destination
- [ ] Each unhonourable URL falls back **and rewrites**
- [ ] A `popstate` produces the destination region's text — and **nothing is asserted about focus**

**Sectors**

- [ ] Ineligible sector grouping below the leaders
- [ ] `k/n` on every row
- [ ] The `<2`-member Δ20d greying
- [ ] Industries ranked only at ≥10 members
- [ ] The pullback note only under CHOPPY/HOSTILE

**Leaders**

- [ ] The `k/5` breadth badge — now a sortable column
- [ ] The `NEW` marker (`new_to_leaders`), scoped to the active lookback
- [ ] ADR toggle — **now defaulting ON**, diverging from v1
- [ ] ~~The ≥30%/5d surge flag on the 1w board~~ — **dropped**, redundant with the return column

**Setups / the sheet**

- [ ] Star score to one decimal as the sort key
- [ ] The eight-row breakdown **reconstructing the score arithmetically**
- [ ] The sheet swaps content in place; the source card stays lit
- [ ] A name with bars but no detection draws the chart with one explicit no-base line

**Markup that dies with its component and is *not* ported**

- `aria-current` on `Workbench` / `Boards` nav buttons — both names are gone
- Every assertion treating the chart panel as a persistent rail
- `toHaveClass("affordable")` and `getByTitle(…)` — the two v1 assertions that already broke the
  role/name contract

---

## Appendix B — the nineteen decisions, indexed

| # | Ticket | Lands in |
|---|---|---|
| 53 | [Does the screening dashboard grade a candidate, or only rank it?](https://github.com/ajitimur/screening-dashboard/issues/53) | [§2.1](#21-the-verdict--what-the-detector-found), [§2.2](#22-the-score--how-the-detected-names-are-ordered), [§11.1](#111-the-35-cut-is-load-bearing-on-an-unvalidated-rubric) |
| 54 | [What q-scanner computes behind the screens this backend cannot feed](https://github.com/ajitimur/screening-dashboard/issues/54) | [§4](#4-the-backend-contract) (input); detail on branch `research/q-scanner-computations` |
| 55 | [q-scanner's design tokens as a Tailwind theme](https://github.com/ajitimur/screening-dashboard/issues/55) | [§3.2](#32-tokens) |
| 56 | [The v2 screen inventory and navigation model](https://github.com/ajitimur/screening-dashboard/issues/56) | [§3.3](#33-chrome), [§3.4](#34-market-and-what-a-market-switch-does), [§5](#5-the-screens), [§5.6](#56-cross-screen-navigation) |
| 57 | [How a chart is opened](https://github.com/ajitimur/screening-dashboard/issues/57) | [§6](#6-the-chart-sheet) |
| 58 | [The backend contract the v2 frontend needs](https://github.com/ajitimur/screening-dashboard/issues/58) | [§4](#4-the-backend-contract), [§1.4](#14-the-phase-1--phase-2-boundary), [§2.3](#23-prices-widths-and-distances) |
| 59 | [The app shell and token set, as a published artifact](https://github.com/ajitimur/screening-dashboard/issues/59) | [§3.1](#31-the-frame), [§3.2](#32-tokens), [§5.1](#51-board) |
| 60 | [The testing posture for a v2 frontend](https://github.com/ajitimur/screening-dashboard/issues/60) | [§9](#9-testing), [Appendix A](#appendix-a--the-behaviour-checklist) |
| 61 | [The Board screen's layout](https://github.com/ajitimur/screening-dashboard/issues/61) | [§5.1](#51-board), [§1.4](#14-the-phase-1--phase-2-boundary) |
| 62 | [The Setups screen's layout](https://github.com/ajitimur/screening-dashboard/issues/62) | [§5.2](#52-setups) |
| 63 | [The Leaders screen's layout](https://github.com/ajitimur/screening-dashboard/issues/63) | [§5.3](#53-leaders), [§4.4](#44-the-leaders-row) |
| 64 | [The Sectors screen and its detail page](https://github.com/ajitimur/screening-dashboard/issues/64) | [§5.4](#54-sectors), [§5.5](#55-sector-detail) |
| 65 | [The empty, loading, error and stale state matrix](https://github.com/ajitimur/screening-dashboard/issues/65) | [§7](#7-empty-loading-error-and-stale) |
| 66 | [The narrow-width floor, if v2 declares one](https://github.com/ajitimur/screening-dashboard/issues/66) | [§1.3](#13-standing-constraints), [§8.1](#81-conformance-statement) |
| 67 | [The accessibility standard v2 holds itself to](https://github.com/ajitimur/screening-dashboard/issues/67) | [§8](#8-accessibility), [§3.2](#32-tokens) |
| 68 | [URL and deep-link state across the v2 shell](https://github.com/ajitimur/screening-dashboard/issues/68) | [§3.5](#35-url-and-history) |
| 69 | [Focus and announcement on a history-driven navigation](https://github.com/ajitimur/screening-dashboard/issues/69) | [§8.8](#88-history-navigation) |
| 70 | [The digest's place in the v2 IA](https://github.com/ajitimur/screening-dashboard/issues/70) | [§1.2](#12-out-of-scope), [§2.4](#24-three-senses-of-new--two-survive-and-they-are-named-apart), [§11.7](#117-the-empty-file-convention-stops-being-an-alerting-mechanism) |
| 71 | [How v2 replaces v1: migration and rollout](https://github.com/ajitimur/screening-dashboard/issues/71) | [§10](#10-migration-and-rollout) |
