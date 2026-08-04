# Sector/theme leadership and rotation model

Type: grilling
Status: resolved
Blocked by: 03, 06

## Question

How does the app decide what is leading, and what does "where the rotation goes" mean concretely?

- **Sector strength metric** — median member return? Share of members in the top decile? Equal-weighted
  vs cap-weighted sector index? Sector ETF price for US (§1 warns he prefers the high-ADR stock over the
  low-ADR ETF, but the ETF may still be the cleanest strength proxy). IDX has no equivalent ETF layer,
  so the metric may have to differ per market — is that acceptable?
- **Cross-market comparability** — one leaderboard spanning IDX + US sectors, or strictly per market?
  Depends on what ticket 03 finds about taxonomies.
- **Rotation, defined** — the ask says "where the rotation goes". Candidates: change in sector rank over
  a window; a relative-rotation-style quadrant (relative strength vs. relative momentum); a flow-of-rank
  visual over successive periods; simply "which sectors newly entered the top". Pick one and define it
  numerically, because the visual follows from the definition.
- **Theme layer — now a sharp ruling, thanks to ticket 03.** The sector axis is settled (Yahoo/
  Morningstar GECS, both markets). Theme is not, and the constraint is specific: **IDX has no thematic
  ETF layer at all**, so the ETF-holdings proxy that works for US produces *nothing* for IDX. The
  choice is therefore about **parity**, not about themes in general:
  - **US-only themes** — free, buildable from ARK/SSGA (ARK serves same-day CSV, SSGA real XLSX;
    iShares, Global X and VanEck need bespoke scrapers and break out of the box). Breaks the map's
    "both markets from day one" constraint for this one feature.
  - **Both markets via LLM tagging** of `longBusinessSummary` (present for >99% of both markets),
    ~$1.75–3.50 per full pass at Haiku 4.5 via the Batch API. Small, but it is a paid line item in an
    otherwise free-data v1, and it needs a re-tagging cadence.
  - **Both markets via correlation clustering** — free, but produces unnamed and unstable clusters,
    which is arguably not a "theme" at all.
  - **Hand-curated** — you maintain the list. Cheapest to build, most honest about how themes actually
    form, costs your time and goes stale silently.
  - **No theme layer in v1** — sector only, theme deferred. Ruled out of scope rather than half-built.

  Whichever wins: how is a stock assigned (one theme or many?), and how does a new theme get added
  mid-quarter? Themes are born fast, and that is exactly when they matter.
- **§10 tie-in** — "pullbacks are information": whatever holds support while the index tests lower is
  showing RS and leads the next leg. Does the app surface that explicitly, or is it emergent from the
  rankings?
- **Sector confirmation in the score** — §3.5 gives "sector/theme confirmation" one point. This ticket
  must define it precisely enough to be computed as a boolean.

Resolve against `references/qullamaggie-method.md` §1 and §10.

## Answer

Every number below is **measured**, not estimated. The session rebuilt the universe from ticket 05's
written decisions alone (median-20d `close × volume` ≥ Rp 1B / $20M, phantom `volume == 0` bars dropped,
≥ 20 non-phantom bars) and got **290 IDX / 1,896 US** against ticket 05's 288 / 1,966 — within 1% and 4%.
That is the third independent session to reproduce the universe. It then pulled sector *and* industry for
**every** surviving name — **289 of 290 IDX and 1,893 of 1,896 US carry a sector** (the 4 misses are
ticket 03's delisting signal, not coverage gaps) — and computed ticket 06's calendar-anchored returns and
per-lookback deciles on top. The share figures below are therefore the real distribution over the whole
universe, not arithmetic on assumed sector sizes or extrapolation from a sample.

### S1 — **Industry *is* the theme layer.** The parity dilemma is dissolved, not decided

Ticket 03 escalated a four-way choice — US-only ETF holdings (breaks "both markets"), LLM tagging (a paid
line item in a free-data v1), correlation clustering (unnamed, unstable), or hand-curation — and all four
are now moot. Yahoo returns **`industry` in the same `.info` request as `sector`**, at no additional cost:
145 industries under the 11 GECS sectors, identical vocabulary on `.JK` and US. Ticket 03 noticed
`Uranium` as "one lucky exception"; it is not an exception, it is the level the whole taxonomy sits at —
`Thermal Coal`, `Solar`, `Semiconductors`, `Biotechnology`, `Gold`, `Steel`, `Marine Shipping`.

So the theme layer is **free, both markets, one request, no scraper, no LLM, no curation, no staleness**,
and v1 stays entirely free-data.

**A stock has exactly one industry**, assigned by Yahoo — so the ticket's "one theme or many?" question
does not arise, and there is no curation backlog.

**Named cost, accepted:** an industry is not a *narrative*. "Nickel downstream" spans Other Industrial
Metals, Steel and Auto Parts; "GLP-1" spans two drug makers plus device names; "AI" spans Semiconductors,
Software-Infrastructure and Utilities. Industry catches a theme when the theme happens to *be* an
industry — which is most of the time on IDX (coal, nickel, gold, banks, agri) and less often on US, where
the loudest themes are cross-industry. A narrative theme layer is therefore **ruled out of scope for v1**
(see the map's Out of scope). You will see the constituent industries move together and read the
narrative yourself.

### S2 — Sector strength = **share of members in that lookback's top decile**, five numbers per sector

One per **1w / 1m / 3m / 6m / 12m** — the same five boards ticket 06 defined — aggregated over its
(name, lookback, night) rank table per R6, so there is **no second definition of "strong."**

**Per-lookback deciles, not the §3.1 union gate.** Ticket 06 measured the union gate at ~29% of the
universe, so a share-of-gate-members metric would sit near 29% for every sector and discriminate poorly.
A per-lookback decile makes **10% the fair share** by construction, so 25–30% is visibly leading and 0%
is visibly dead.

**Rejected:** an equal- or cap-weighted sector index return, and the US sector-ETF proxy. Ticket 06's R6
already gave the reason — a sector where 8 of 40 names are ripping and 32 are flat has a mediocre index
return but is exactly the sector to surface, because leadership concentrates before it broadens. The ETF
route would additionally have needed a *different* metric per market, since IDX has no thematic or
sector-ETF reference layer worth using. Member-rank aggregation is identical on both by construction.

### S3 — Rotation is **two sortable columns**, not a sparkline and not a composite

The session first proposed leaving rotation to the eye — the shape across lookbacks, read off a
sparkline. **The trader overruled it: rotation must be computed and sortable.** Delivered as two columns,
because one number cannot carry both readings:

- **Shape differential** — `share(1w) − share(6m)`, in percentage points. **Zero tunable parameters, no
  history required**, and it cannot drift from ticket 06's definition of strong because it is arithmetic
  on two numbers already on the row. Positive = rotating in, negative = rotating out. **This is the
  default sort.**
- **Temporal delta** — `share(1m, tonight) − share(1m, 20 sessions ago)`. The 20 is **inherited, not
  invented**: §2 puts the daily chart on the 10/20 MAs and §3.5 scores MA support on the 10 and 20, so
  the method already fixes 20 as its swing horizon.

They disagree usefully, which is why both exist: a sector can be structurally hot (high differential)
while its share has been *falling* for a month — a rotation that already happened and is decaying. The
differential alone cannot separate genuine fresh leadership from a one-week dead-cat bounce in a sector
dead for six months.

**No composite of the two, and no threshold on either** — they are columns you sort, not a verdict.

**Named cost:** the temporal delta is the noisiest column on the board. Ticket 06 measured a ~1.5pp noise
floor from denominator churn alone, and on a thin sector one name entering the universe moves the share
several points by itself. Twenty sessions averages some of that out, but not to zero. It carries a noise
caveat in the UI.

### S4 — No sector is ever hidden, but **`k ≥ 2` is required to top the rotation board**

**Measured: quantization is an IDX problem and it lands squarely on S3's default sort.** IDX's smallest
Morningstar sector is Utilities at **10 members**, then Technology and Healthcare at 14; the largest is
Industrials at 43 — so nothing is thin enough to *exclude*, and an exclusion floor is moot. But one name
entering the decile moves **Utilities' share by 10.0pp** and Technology's by 7.1pp, against Industrials'
2.3pp. In the measured snapshot **Technology topped the IDX rotation differential at +21.4pp**, which is
**three stocks** in the 1w decile against zero in the 6m. Sorted freely, the IDX rotation board would be
led by its smallest sectors on most nights.

So: **a sector needs at least 2 members in the shorter lookback's decile to be eligible for the top of
the rotation board.** Single-name sectors sort into a separate group below it, still visible with their
numbers intact. **Every row carries `k/n` beside the share** — `2/9` reads as fragile where `22.2%` reads
as leadership, the same device ticket 06 used with its `k/5` breadth badge.

`k ≥ 2` is not a tuned threshold; it is **§10's "strength clusters" stated literally — one stock is not a
sector rotating.**

**Rejected: shrinkage toward the 10% baseline.** That is a smoothing parameter on the noisiest input on
the map, and ticket 06 already rejected smoothing on the same grounds.

On US the rule is nearly a no-op — the smallest US sector is Utilities at 59 members and the largest
Technology at 340, so one name moves a US sector share by only **0.3–1.7pp** — which is the correct
behaviour for a rule that exists to catch thin markets.

### S5 — **One industry board**, and a ranked industry needs `n ≥ 10`

**IDX cannot support an industry leaderboard on its own numbers**: **87 industries** across its 289
names, **median size 2**, **38 industries with exactly one member**, only 7 with ten or more. The shares
are noise by construction — Real Estate Services reads **57.1% on 1m, which is 4 names of 7**.

**US can**: **139 industries, median size 9, only 5 singletons, and 63 at ten or more** — with real mass
in the head: Biotechnology 107, Software-Application 85, Banks-Regional 80, Software-Infrastructure 75,
Semiconductors 44.

The ruling is **one rule applied identically to both markets: an industry is ranked if it has ≥ 10
members.** That yields **63 rows on US and exactly 7 on IDX** (Banks-Regional 19, Farm Products 18,
Real Estate-Development 17, Thermal Coal 15, Packaged Foods 12, Marine Shipping 12, Other Industrial
Metals & Mining 10). **Parity of rule, not parity of result** — the market's own data density decides the
yield and no market is special-cased. An IDX industry board reading Thermal Coal / Farm Products / Marine
Shipping / Other Industrial Metals is not degenerate; those are close to the actual Indonesian themes.

**`n ≥ 10` is derived, not picked**: it is exactly the point at which one name can move the share by at
most 10pp — the decile baseline itself. Below it, a single stock can swing an industry by more than its
entire fair share.

Industries below the floor are **not hidden** — they remain as the per-candidate tag (S6), just unranked.

### S6 — §3.5 sector/theme confirmation = **leave-one-out sector share ≥ 10% on the 1m lookback**

The measurement caught a trap that would otherwise have shipped. The obvious rule — "the candidate's
sector share is ≥ the 10% baseline" — fires **77–90%** of the time, and not because sectors are hot: it
is a **selection effect**. The stock being tested is itself in the top decile, and its own membership
inflates its own sector's share. The point would be nearly free, and a dimension that fires 90% of the
time carries no information in a 10-point rubric.

Computing the share **leave-one-out** — excluding the candidate from its own sector's numerator *and*
denominator — fixes it exactly, dropping the rule to a **stable 52% on IDX across 1m, 3m and 6m**. For
one point out of ten, firing about half the time is where a binary belongs.

**Rejected: the industry-peer rule** ("at least one *other* name in this stock's industry is also in the
decile"). It is closer to §10's "strength clusters," but it measured **24–55% on IDX against a flat
88–89% on US** — so the same rubric line would be a coin-flip in one market and nearly free in the other.
It is also **structurally unavailable to many IDX names**: 38 IDX industries have exactly one member, so
those stocks could never earn the point however strong their theme.

**1m rather than the lookback the stock qualified on**, because §3.5 already scores the stock's own
momentum separately under "prior move strength (top decile 1–6m)". This dimension asks whether the
*sector* is hot now, and 1m is the shortest read that is not 1w noise.

**Industry appears on the candidate row as context** — "Thermal Coal, 20% of members in the 1m decile" —
but **does not score**, so no name is penalised for being alone in its industry.

**Named cost, accepted:** the rule is not symmetric across markets. It fires **52% on IDX — identical on
1m, 3m and 6m — but 61–79% on US**. It still discriminates on both (the all-names baseline is 36–46%),
and it is far more stable than the industry-peer alternative it replaced.

### S7 — §10's "pullbacks are information" is **emergent**, not a feature

A decile is **cross-sectional** — always a ranking against the rest of the market, never against zero.
So in a market that fell 8% over the past month, the names in the 1m top decile *are* the names that held
up. **The sector shares computed on a falling tape already are the pullback-RS reading.** There is
nothing to add and nothing to tune.

Making it explicit would have required detecting "the most recent pullback," which needs a drawdown
threshold and a window — and ticket 10 drove the regime filter to *zero* tunables precisely because
survivorship bias makes thresholds like that uncalibratable.

**Surfaced as copy, not computation:** when ticket 10's regime banner reads `CHOPPY` or `HOSTILE`, the
sector board carries a one-line note that these shares are reading relative strength through a decline.

**Named limit:** §10 also says the *deep washout* case inverts — the first bounce is led by the most
beaten-down junk, not the RS names. The shares cannot distinguish a mild pullback from a washout, because
that requires measuring drawdown depth, which ticket 10 deliberately declined to measure. So in a washout
the board points at RS names during the exact regime where §10 says RS names are not the ones that bounce
first. The note states this.

### S8 — Sector strength **never filters**; every sector always renders; computed per market

- **Never filters.** It contributes its one point to the star score (S6) and it is a board you read. It
  does not gate, reorder, or remove candidates. Direct parallel to ticket 10's advisory-only regime
  filter and ticket 06's report-rather-than-judge stance.
- **All 11 sectors always render**, both markets, even at 0% on every lookback. A dead sector is
  information, and hiding it would violate ticket 05's "absence of data means nothing."
- **Computed per market, displayed on a shared axis.** Ticket 03 measured Technology at 27% of its US
  sample and 1% of its IDX sample, so a pooled cross-market ranking would make "Technology is leading on
  IDX" a statement about one or two stocks. Ticket 06 already fixed ranking as per-market. Two rankings,
  one 11-sector axis, side by side.
- **Layout belongs to ticket 11.** This ticket fixes the numbers and the eligibility rules only.

### S9 — Sector/industry cache: new names block, 1/30th rolls nightly, a failed fetch never nulls

Ticket 03 established that sector costs **one request per symbol**. This session measured the full
universe at **1.2s spacing with zero throttling across ~1,850 consecutive calls** (every row returned
`ok`; the only non-`ok` values were the 4 genuine `no_sector` delistings) — so ticket 03's 2s
recommendation was conservative, and a full pass is ~48 minutes rather than 75. Still far too long for
the nightly job.

- **New names block.** A symbol entering the universe has sector/industry fetched *before* it can appear
  anywhere — a name with no industry cannot be placed on the axis, so this is correctness, not cost. At
  ticket 05's measured churn (~30 US / ~8 IDX a night) that is under 90 requests, ~2 minutes.
- **Existing names refresh on a rolling 1/30th slice nightly** — ~73 names, ~2 minutes — so the whole
  universe turns over every 30 days with no wholesale pass and bounded staleness. Nightly cost stays flat
  as the universe grows.
- **A failed fetch never nulls a cached value.** Straight from ticket 03's "Yahoo throttling fails as
  silence" and ticket 05's "removal requires stronger evidence than admission": on throttle or error the
  name keeps yesterday's industry and is retried, never blanked.

Net: ~4 minutes added to the nightly run, worst-case 30-day staleness on reclassification, **zero**
staleness on new names — which is what the ticket's "themes are born fast, and that is exactly when they
matter" actually demanded.

### Hand-offs

- **→ Ticket 11 (dashboard IA):** three boards to lay out per market — 11 sector rows with five shares
  plus two rotation columns; the ranked-industry board; and the per-candidate industry tag. Plus the
  regime-conditional pullback note (S7) and the `k/n` fragility device (S4).
- **→ Ticket 08 (setup detection):** S6 is the computable boolean for the §3.5 "sector/theme
  confirmation" line — leave-one-out sector share ≥ 10% on 1m.
- **→ Ticket 12 (architecture):** sector/industry is a cached table with the S9 refresh policy, and
  nightly sector-share history is a **fifth** persisted stream (see the map's validation fog).
