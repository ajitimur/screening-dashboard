import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Panel, NightEmpty, useBodyRead } from "./Panel";
import ChartSheet, { type SheetTarget } from "./ChartSheet";
import {
  fetchSectorDetail,
  fetchSectors,
  type IndustryStrength,
  type SectorDetailResponse,
  type SectorMember,
  type SectorStrength,
  type SectorsResponse,
} from "./api/client";

// ── The Sectors screen and its drill-down (spec §5.4 / §5.5) ─────────────────
//
// Sectors is STACKED BANDS, not peer panels side by side (spec §5.4): the decile
// table is too wide to sit beside a square plot, so the two rotation models
// stack. Phase 1 is a finished TWO-band screen — the decile-share model and the
// market-wide industry board — with NO reserved slot for the phase-2 RRG plot,
// which appends *above* purely additively when it lands.
//
// The drill-down (sector detail) is not a tab: it keeps the Sectors tab lit and
// the breadcrumb is the honest control (spec §5.5). Every sector-bearing mark on
// the list is a real <button> into detail; an industry row drills into its
// PARENT sector. Ineligible/thin sectors stay visible and still click through —
// a thin sector is still a sector you can open, not an empty state.

// The five ranking lookbacks, shortest first (spec §4.3). Display labels adopt
// the uppercase form (spec §5.3) while the keys stay v1's.
const LOOKBACKS = [
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "12m", label: "12M" },
] as const;
type Lookback = (typeof LOOKBACKS)[number]["key"];

// The detail lookback defaults to 1m, matching the Board strip (spec §5.5).
const DEFAULT_LOOKBACK: Lookback = "1m";

// The regime states that carry the pullback note (spec §5.4). It is attached to
// the decile band ONLY and only under the two weaker regimes — the permanent
// band says *what* the regime is, the note says what a CHOPPY/HOSTILE regime
// does to the *meaning* of decile share.
type Regime = "FRIENDLY" | "CHOPPY" | "HOSTILE";

function pct(share: number): string {
  return `${Math.round(share * 100)}%`;
}

function signedPct(value: number): string {
  const p = Math.round(value * 100);
  return `${p > 0 ? "+" : ""}${p}pp`;
}

// A signed percentage return, e.g. "+12%" / "−4%".
function signedReturn(value: number): string {
  const p = Math.round(value * 100);
  return `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p)}%`;
}

/**
 * The Sectors tab (spec §5.4/§5.5). One component owns both the list and the
 * drill-down, so the focus intent that distinguishes the two back-doors — the
 * breadcrumb restores the drilled row, the lit tab and browser-back do not —
 * survives the list↔detail swap without a shared parent state (spec §8.6/§8.8).
 */
export default function Sectors({
  market,
  sector,
  regime,
  navigate,
}: {
  market: string;
  sector: string | null;
  regime: Regime | null;
  navigate: (patch: { sector?: string | null }) => void;
}) {
  // Focus management (spec §8.6): a drill-in moves focus to the detail heading;
  // breadcrumb-back restores focus to the exact row that was drilled into. Both
  // are USER acts, so the intent is set explicitly — a browser-back or a lit-tab
  // return sets neither and so moves no focus (spec §8.8, the asymmetry that is
  // the rule working). The intent lives in a ref, not state, so the row-restore
  // can fire from the row's own ref callback: the list re-fetches on return, so
  // the drilled row does not exist yet when a render effect would run — it must
  // be focused the moment it (re)mounts. `restoreKey` names the origin row (a
  // sector or an industry row), so an industry drill restores the industry row.
  const pendingFocusRef = useRef<"heading" | "row" | null>(null);
  const restoreKeyRef = useRef<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const registerRow = useCallback((key: string, el: HTMLButtonElement | null) => {
    if (el && pendingFocusRef.current === "row" && restoreKeyRef.current === key) {
      el.focus();
      pendingFocusRef.current = null;
    }
  }, []);

  // Drill into a sector's detail. `originKey` is the row that was pressed, so
  // breadcrumb-back can return focus to it later; `target` is the sector opened
  // (an industry row opens its parent sector, so the two differ there).
  const drillInto = useCallback(
    (originKey: string, target: string) => {
      restoreKeyRef.current = originKey;
      pendingFocusRef.current = "heading";
      navigate({ sector: target });
    },
    [navigate],
  );

  const breadcrumbBack = useCallback(() => {
    pendingFocusRef.current = "row";
    navigate({ sector: null });
  }, [navigate]);

  // The detail heading renders immediately (its text is the URL sector, not a
  // fetch), so a render effect keyed on `sector` focuses it reliably on drill-in.
  useEffect(() => {
    if (pendingFocusRef.current === "heading" && sector) {
      headingRef.current?.focus();
      pendingFocusRef.current = null;
    }
  }, [sector]);

  if (sector) {
    return (
      <section
        id="active-tabpanel"
        role="tabpanel"
        aria-labelledby="tab-sectors"
        tabIndex={0}
      >
        <SectorDetail
          market={market}
          sector={sector}
          headingRef={headingRef}
          onBreadcrumbBack={breadcrumbBack}
        />
      </section>
    );
  }

  return (
    <section
      id="active-tabpanel"
      role="tabpanel"
      aria-labelledby="tab-sectors"
      tabIndex={0}
    >
      <h2>Sectors</h2>
      <SectorList
        market={market}
        regime={regime}
        onDrill={drillInto}
        registerRow={registerRow}
      />
    </section>
  );
}

// ── The list: two stacked bands (spec §5.4) ──────────────────────────────────

function SectorList({
  market,
  regime,
  onDrill,
  registerRow,
}: {
  market: string;
  regime: Regime | null;
  onDrill: (originKey: string, target: string) => void;
  registerRow: (key: string, el: HTMLButtonElement | null) => void;
}) {
  // Both bands are one fetch (spec §4.5), so they share one body read: they
  // load, switch and fail together, which is honest for a single resource.
  const read = useBodyRead<SectorsResponse>(market, fetchSectors);

  return (
    <div className="sectors-bands">
      {/* Band 1 — the decile-share model at full width (spec §5.4). */}
      <Panel
        label="Where the leaders are clustered"
        read={read}
        skeleton={<div className="band-skeleton" style={{ height: 320 }} />}
      >
        {(data) => (
          <DecileBand
            data={data}
            regime={regime}
            onDrill={onDrill}
            registerRow={registerRow}
          />
        )}
      </Panel>

      {/* Band 2 — the market-wide industry leadership board (spec §5.4). */}
      <Panel
        label="Industry leadership"
        read={read}
        skeleton={<div className="band-skeleton" style={{ height: 200 }} />}
      >
        {(data) => (
          <IndustryBand data={data} onDrill={onDrill} registerRow={registerRow} />
        )}
      </Panel>
    </div>
  );
}

// The two sortable rotation columns (spec §5.4). Shape is the default; a thin
// single-name sector can never top either (the k≥2 eligibility guard).
type SortKey = "shape" | "temporal";

// The five per-lookback share cells with their k/n fragility badge — the
// hard-won read v1 shipped, ported (spec §5.4).
type ShareRow = Pick<SectorStrength, "shares" | "decile_counts" | "members">;

function ShareCells({ row }: { row: ShareRow }) {
  return (
    <>
      {LOOKBACKS.map(({ key }) => (
        <td key={key} className="share">
          {pct(row.shares[key])}{" "}
          <span className="kn">
            {row.decile_counts[key]}/{row.members}
          </span>
        </td>
      ))}
    </>
  );
}

/**
 * Band 1, "Where the leaders are clustered" (spec §5.4): v1's decile-share model
 * at full width. Five lookbacks with k/n fragility badges, shape differential,
 * Δ20d, and the k≥2 eligibility guard sinking thin sectors into a below-fold
 * group — **ported, not rewritten** (the guard is hard-won logic, not layout).
 * Every sector row is a real <button> into detail; ineligible sectors stay
 * visible and still click through (they are not empty states).
 */
function DecileBand({
  data,
  regime,
  onDrill,
  registerRow,
}: {
  data: SectorsResponse;
  regime: Regime | null;
  onDrill: (originKey: string, target: string) => void;
  registerRow: (key: string, el: HTMLButtonElement | null) => void;
}) {
  const [sort, setSort] = useState<SortKey>("shape");

  // Sort within the eligibility groups: rotation-ineligible sectors always sort
  // below the eligible ones (the k≥2 guard), and within each group by the chosen
  // rotation column descending. Ported verbatim from v1's SectorTable.
  const sorted = useMemo(() => {
    const value = (s: SectorStrength) =>
      sort === "shape" ? s.shape_differential : s.temporal_delta ?? -Infinity;
    return [...data.sectors].sort((a, b) => {
      if (a.rotation_eligible !== b.rotation_eligible)
        return a.rotation_eligible ? -1 : 1;
      return value(b) - value(a);
    });
  }, [data.sectors, sort]);

  const firstIneligible = sorted.findIndex((s) => !s.rotation_eligible);
  // The pullback note appears only on the decile band and only under the two
  // weaker regimes (spec §5.4).
  const showPullbackNote = regime === "CHOPPY" || regime === "HOSTILE";

  return (
    <>
      <p className="band-subtitle">share of the top momentum decile · five lookbacks</p>
      {showPullbackNote && (
        <p role="note" className="pullback-note">
          The market is {regime}: these shares read relative strength through a
          decline. They cannot tell a mild pullback from a washout, where the
          first bounce leads with the most beaten-down names.
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th scope="col">Sector</th>
            {LOOKBACKS.map(({ key, label }) => (
              <th scope="col" key={key}>
                {label}
              </th>
            ))}
            <th scope="col">
              <button
                type="button"
                aria-pressed={sort === "shape"}
                onClick={() => setSort("shape")}
              >
                Δ shape (1w−6m)
              </button>
            </th>
            <th scope="col">
              <button
                type="button"
                aria-pressed={sort === "temporal"}
                onClick={() => setSort("temporal")}
              >
                Δ20d (1m)
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, i) => {
            const key = `sector:${s.sector}`;
            return (
              <tr
                key={s.sector}
                className={
                  s.rotation_eligible ? "eligible" : "rotation-ineligible"
                }
                data-group-start={
                  i === firstIneligible ? "ineligible" : undefined
                }
              >
                <th scope="row">
                  <button
                    type="button"
                    className="sector-link"
                    ref={(el) => registerRow(key, el)}
                    onClick={() => onDrill(key, s.sector)}
                  >
                    {s.sector}
                  </button>
                </th>
                <ShareCells row={s} />
                <td className="shape">{signedPct(s.shape_differential)}</td>
                <td
                  className={
                    s.delta_low_confidence
                      ? "temporal low-confidence"
                      : "temporal"
                  }
                >
                  {s.temporal_delta === null
                    ? "—"
                    : signedPct(s.temporal_delta)}
                  {s.delta_low_confidence && s.temporal_delta !== null && (
                    <abbr title="rests on fewer than two decile members"> †</abbr>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

/**
 * Band 2, the industry leadership board (spec §5.4): kept **market-wide** rather
 * than pushed onto detail, so *"Semiconductors leads everything"* stays a
 * top-level fact. Every industry row is a <button> that drills into its PARENT
 * sector's detail — the industry is the theme, the sector is the pack.
 */
function IndustryBand({
  data,
  onDrill,
  registerRow,
}: {
  data: SectorsResponse;
  onDrill: (originKey: string, target: string) => void;
  registerRow: (key: string, el: HTMLButtonElement | null) => void;
}) {
  if (data.industries.length === 0)
    return (
      <>
        <p className="band-subtitle">≥10-member industries · market-wide</p>
        <NightEmpty>No industry has 10 or more members to rank.</NightEmpty>
      </>
    );

  return (
    <>
      <p className="band-subtitle">≥10-member industries · market-wide</p>
      <table>
        <thead>
          <tr>
            <th scope="col">Industry</th>
            <th scope="col">Sector</th>
            {LOOKBACKS.map(({ key, label }) => (
              <th scope="col" key={key}>
                {label}
              </th>
            ))}
            <th scope="col">Δ shape</th>
          </tr>
        </thead>
        <tbody>
          {data.industries.map((ind: IndustryStrength) => {
            const key = `industry:${ind.industry}`;
            return (
              <tr key={ind.industry}>
                <th scope="row">
                  <button
                    type="button"
                    className="sector-link"
                    ref={(el) => registerRow(key, el)}
                    onClick={() => onDrill(key, ind.sector)}
                  >
                    {ind.industry}
                  </button>
                </th>
                <td>{ind.sector}</td>
                <ShareCells row={ind} />
                <td className="shape">{signedPct(ind.shape_differential)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

// ── The drill-down: sector detail (spec §5.5) ────────────────────────────────

/**
 * The sector detail page (spec §5.5): what is inside this pack. Columns are
 * `# · ticker · {lookback} return · pctile-in-universe · decile badge`. The
 * decile badge is per the selected lookback and re-renders on switch (this
 * repo's decile is per-lookback where the reference has one). Lookback defaults
 * to 1m; the top-decile toggle is phase 1. ADR% and dollar volume are dropped,
 * not reserved. The ticker opens the one docked chart sheet.
 *
 * Two back-doors, both keyboard-reachable: the `Sectors / <name>` breadcrumb
 * (its first segment a real <button>) and the lit Sectors tab. They behave
 * differently on purpose (spec §8.6) — the breadcrumb restores the drilled row,
 * handled by the parent; the tab gets the tab treatment.
 */
function SectorDetail({
  market,
  sector,
  headingRef,
  onBreadcrumbBack,
}: {
  market: string;
  sector: string;
  headingRef: React.RefObject<HTMLHeadingElement>;
  onBreadcrumbBack: () => void;
}) {
  const [lookback, setLookback] = useState<Lookback>(DEFAULT_LOOKBACK);
  const [topDecileOnly, setTopDecileOnly] = useState(false);
  // The one docked chart sheet (spec §6): its target is the open ticker, nulled
  // on user close. Detail members carry no chart-facts fold, so the sheet falls
  // back to the chart read for facts/breakdown (spec §6.3, the Leaders case).
  const [sheet, setSheet] = useState<SheetTarget | null>(null);

  // The fetcher closes over the sector, so it must be re-created only when the
  // sector changes — otherwise `useBodyRead`'s effect re-fires every render.
  const fetcher = useCallback(
    (m: string) => fetchSectorDetail(m, sector),
    [sector],
  );
  const read = useBodyRead<SectorDetailResponse>(market, fetcher);

  return (
    <div className="sector-detail">
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <button
          type="button"
          className="breadcrumb-back"
          onClick={onBreadcrumbBack}
        >
          Sectors
        </button>
        <span aria-hidden="true"> / </span>
        <span className="breadcrumb-current">{sector}</span>
      </nav>
      <h2 ref={headingRef} tabIndex={-1}>
        {sector}
      </h2>

      <LookbackControl lookback={lookback} onSelect={setLookback} />
      <button
        type="button"
        className="top-decile-toggle"
        aria-pressed={topDecileOnly}
        onClick={() => setTopDecileOnly((v) => !v)}
      >
        Top decile only
      </button>

      <Panel
        label={`${sector} members`}
        read={read}
        skeleton={<div className="band-skeleton" style={{ height: 320 }} />}
      >
        {(data) => (
          <MemberTable
            data={data}
            lookback={lookback}
            topDecileOnly={topDecileOnly}
            market={market}
            onOpen={setSheet}
          />
        )}
      </Panel>

      <ChartSheet target={sheet} onClose={() => setSheet(null)} />
    </div>
  );
}

/**
 * The lookback switch (spec §5.5): the five this repo ranks, as a `radiogroup`
 * (it re-shapes the same rows, it does not reveal a sibling panel). Default 1m.
 */
function LookbackControl({
  lookback,
  onSelect,
}: {
  lookback: Lookback;
  onSelect: (lb: Lookback) => void;
}) {
  return (
    <div role="radiogroup" aria-label="Lookback" className="lookback-control">
      {LOOKBACKS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={key === lookback}
          className="lookback-item"
          onClick={() => onSelect(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * The member table (spec §5.5). Ranked by the selected lookback's return, so `#`
 * is a leaderboard position within the pack; a name not ranked in that lookback
 * (a recent listing) sorts last and shows `—`. The percentile column names its
 * population explicitly (this repo ranks over the whole universe, applying no
 * tradability filter). The decile badge is per the selected lookback.
 */
function MemberTable({
  data,
  lookback,
  topDecileOnly,
  market,
  onOpen,
}: {
  data: SectorDetailResponse;
  lookback: Lookback;
  topDecileOnly: boolean;
  market: string;
  onOpen: (target: SheetTarget) => void;
}) {
  const rows = useMemo(() => {
    const ranked = data.members.filter((m) => topDecileOnly ? m.top_decile[lookback] : true);
    return [...ranked].sort((a, b) => {
      const ra = a.returns[lookback];
      const rb = b.returns[lookback];
      // Names not ranked in this lookback sort last; among ranked, higher return
      // first. `(-return, symbol)` mirrors the board tie-break.
      const av = ra === undefined ? -Infinity : ra;
      const bv = rb === undefined ? -Infinity : rb;
      if (av !== bv) return bv - av;
      return a.symbol.localeCompare(b.symbol);
    });
  }, [data.members, lookback, topDecileOnly]);

  if (rows.length === 0)
    return (
      <NightEmpty>
        {topDecileOnly
          ? `No ${data.sector} name is top-decile at this lookback.`
          : `No names in ${data.sector} tonight.`}
      </NightEmpty>
    );

  return (
    <table className="member-table">
      <caption className="sr-only">
        {data.sector} members ranked by {lookback} return
      </caption>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Ticker</th>
          <th scope="col">Return</th>
          <th scope="col">Percentile (universe)</th>
          <th scope="col">Decile</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m: SectorMember, i) => {
          const ret = m.returns[lookback];
          const pctile = m.pctile_universe[lookback];
          const ranked = ret !== undefined;
          return (
            <tr key={m.symbol}>
              <td className="rank">{i + 1}</td>
              <th scope="row">
                <button
                  type="button"
                  className="ticker-link"
                  onClick={() => onOpen({ symbol: m.symbol, market })}
                >
                  {m.symbol}
                </button>
              </th>
              <td className="member-return">
                {ranked ? (
                  <>
                    <span
                      className="return-bar"
                      aria-hidden="true"
                      style={{ width: `${Math.min(100, Math.abs(ret) * 100)}%` }}
                    />
                    <span className="return-value">{signedReturn(ret)}</span>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td className="member-pctile">
                {pctile === undefined ? "—" : Math.round(pctile * 100)}
              </td>
              <td className="member-decile">
                {m.top_decile[lookback] ? (
                  <span className="decile-badge">Top decile</span>
                ) : (
                  <span className="decile-badge-empty">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
