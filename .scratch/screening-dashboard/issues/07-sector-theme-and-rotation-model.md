# Sector/theme leadership and rotation model

Type: grilling
Status: open
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
