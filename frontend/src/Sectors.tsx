import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Panel, NightEmpty, useBodyRead } from "./Panel";
import ChartSheet, { type SheetTarget } from "./ChartSheet";
import SectorMap from "./SectorMap";
import {
  fetchSectorDetail,
  fetchSectors,
  type SectorDetailResponse,
  type SectorMember,
  type SectorsResponse,
} from "./api/client";

// ── The Sectors screen and its drill-down (spec §5.4 / §5.5) ─────────────────
//
// The list is ONE panel: the rotation map (SectorMap) — a summary sentence, a
// plot of six-month leader share against this-week leader share, and a ranked
// list beside it that names each sector's rotation state and the industries
// carrying it. It replaced the two stacked bands (the decile table and the
// market-wide industry board) after a prototype; the decile-share model and the
// k≥2 eligibility guard underneath are unchanged, the map only *reads* them.
//
// The drill-down (sector detail) is not a tab: it keeps the Sectors tab lit and
// the breadcrumb is the honest control (spec §5.5). Every sector-bearing mark on
// the list is a real <button> into detail; an industry drills into its PARENT
// sector. Ineligible/thin sectors stay visible and still click through — a thin
// sector is still a sector you can open, not an empty state.

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

// A signed percentage return, e.g. "+12%" / "−4%" (a typographic minus).
function signedReturn(value: number): string {
  const p = Math.round(value * 100);
  let sign = "";
  if (p > 0) sign = "+";
  else if (p < 0) sign = "−";
  return `${sign}${Math.abs(p)}%`;
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

  // The list and the detail share one `tabpanel` shell so the drill-down never
  // reopens the tabpanel contract (id/role/labelling) in two places.
  return (
    <section
      id="active-tabpanel"
      role="tabpanel"
      aria-labelledby="tab-sectors"
      tabIndex={0}
    >
      {sector ? (
        <SectorDetail
          market={market}
          sector={sector}
          headingRef={headingRef}
          onBreadcrumbBack={breadcrumbBack}
        />
      ) : (
        <>
          <h2>Sectors</h2>
          <SectorList
            market={market}
            regime={regime}
            onDrill={drillInto}
            registerRow={registerRow}
          />
        </>
      )}
    </section>
  );
}

// ── The list: the rotation map (spec §5.4) ───────────────────────────────────

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
  const read = useBodyRead<SectorsResponse>(market, fetchSectors);
  // The pullback note (spec §5.4): only under the two weaker regimes. The
  // permanent regime band says *what* the regime is; the note says what a
  // CHOPPY/HOSTILE regime does to the *meaning* of decile share.
  const showPullbackNote = regime === "CHOPPY" || regime === "HOSTILE";

  return (
    <div className="sectors-bands">
      <Panel
        label="Sector rotation"
        read={read}
        skeleton={<div className="band-skeleton" style={{ height: 420 }} />}
      >
        {(data) => (
          <>
            {showPullbackNote && (
              <p role="note" className="pullback-note">
                The market is {regime}: these shares read relative strength
                through a decline. They cannot tell a mild pullback from a
                washout, where the first bounce leads with the most beaten-down
                names.
              </p>
            )}
            <SectorMap data={data} onDrill={onDrill} registerRow={registerRow} />
          </>
        )}
      </Panel>
    </div>
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
    const visible = data.members.filter(
      (m) => !topDecileOnly || m.top_decile[lookback],
    );
    return visible.sort((a, b) => {
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
