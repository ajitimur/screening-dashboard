import { useEffect, useMemo, useState } from "react";
import { fetchLeaders, type Leader, type LeaderRow } from "./api/client";
import { Panel, FilterEmpty, NightEmpty, useBodyRead } from "./Panel";
import ChartSheet, { type SheetTarget } from "./ChartSheet";
import MiniChart from "./MiniChart";

/**
 * Screen 3 — Leaders (spec §5.3). v1's five-up is **retired**: one table with a
 * lookback segmented control, and `k/5` — the breadth count that the five-up only
 * ever gestured at — is promoted to a **sortable column**, which is strictly more
 * than the glance gave (you can now rank by persistence).
 *
 * Both the table and the grid share ONE row model, ONE sort and ONE filter set
 * (spec §5.3): the view toggle is a pure re-render of the same rows. The grid is
 * the mini-chart surface.
 */

// v1's five lookbacks under **v1's keys** — the contract, the store and
// `SURGE_THRESHOLD` all say `1w` (spec §5.3). Only the display *labels* adopt the
// reference's upper casing. 18M is P2; **the `k/5` denominator is pinned to these
// five by definition** — an 18M column would be sortable but must not count toward
// breadth, or every historical `4/5` silently changes meaning.
const LOOKBACKS = [
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "12m", label: "12M" },
] as const;
type LookbackKey = (typeof LOOKBACKS)[number]["key"];

// Table / grid: a `radiogroup`, not an on/off — the grid is the mini-chart
// surface, a peer view not a modifier (spec §5.3).
const VIEWS = [
  { key: "table", label: "Table" },
  { key: "grid", label: "Grid" },
] as const;
type ViewKey = (typeof VIEWS)[number]["key"];

// Sub-4% ADR is the floor the one toggle hides (spec §5.3). A fraction of price.
const LOW_ADR = 0.04;

// The four sortable columns (spec §5.3): return is the default and the primary
// key, `k/5`, ADR% and $vol are the others. The tier band is P2.
type SortKey = "return" | "breadth" | "adr" | "dvol";
interface SortState {
  key: SortKey;
  dir: "asc" | "desc";
}
const SORT_LABELS: Record<SortKey, string> = {
  return: "return",
  breadth: "breadth",
  adr: "ADR",
  dvol: "dollar volume",
};

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

// Compact dollar volume, e.g. "$1.2M" — the §4.1 median-20d liquidity number.
function formatDollarVolume(value: number): string {
  return `$${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

// The value a sort key reads off a row; `null` for the two nullable columns so a
// name whose ADR or dollar volume could not be computed sorts to the bottom in
// either direction rather than jumping to the top of an ascending sort.
function sortValue(row: LeaderRow, key: SortKey): number | null {
  if (key === "return") return row.raw_return;
  if (key === "breadth") return row.breadth;
  if (key === "adr") return row.adr;
  return row.dollar_volume;
}

// Order rows by the active sort, `symbol` ascending as the stable tie-break — the
// same `(-raw_return, symbol)` shape `boards.py` ranks by, generalised to any
// column. Nulls always sink, regardless of direction.
function sortRows(rows: LeaderRow[], sort: SortState): LeaderRow[] {
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = sortValue(a, sort.key);
    const vb = sortValue(b, sort.key);
    if (va === null && vb === null) return a.symbol.localeCompare(b.symbol);
    if (va === null) return 1;
    if (vb === null) return -1;
    if (va !== vb) return (va - vb) * sign;
    return a.symbol.localeCompare(b.symbol);
  });
}

export default function Leaders({ market }: { market: string }) {
  const read = useBodyRead(market, fetchLeaders);

  // ── View-shape state — SURVIVES a market switch (spec §3.4) ────────────────
  const [lookback, setLookback] = useState<LookbackKey>("1w");
  const [sort, setSort] = useState<SortState>({ key: "return", dir: "desc" });
  const [view, setView] = useState<ViewKey>("table");
  // The one liquidity floor an ungated universe has, so it **defaults ON** — a
  // deliberate divergence from v1 (spec §5.3). Its consequence is that a user can
  // hit a zero-row table having never touched a control, which must read as
  // filter-inflicted (handled below).
  const [hideLowAdr, setHideLowAdr] = useState(true);
  const [sector, setSector] = useState("");

  // ── Entity-naming state — RESETS on a market switch (spec §3.4) ────────────
  // The open sheet's symbol and the ticker query name specific entities, so they
  // are cleared when the market changes (the reset rule the shell delegates here).
  const [ticker, setTicker] = useState("");
  const [target, setTarget] = useState<SheetTarget | null>(null);
  useEffect(() => {
    setTicker("");
    setTarget(null);
  }, [market]);

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
  }

  function clearFilters() {
    setHideLowAdr(false);
    setSector("");
    setTicker("");
  }

  function openSheet(row: LeaderRow) {
    // Leaders has no candidate fold, so it passes only the navigable symbol (plus
    // the sector it happens to carry) — the sheet falls back to the chart read for
    // facts and breakdown (spec §6.3).
    setTarget({ symbol: row.symbol, market, sector: row.sector, facts: null, breakdown: null });
  }

  return (
    <>
      <ControlBar
        lookback={lookback}
        onLookback={setLookback}
        view={view}
        onView={setView}
        ticker={ticker}
        onTicker={setTicker}
        sector={sector}
        onSector={setSector}
        hideLowAdr={hideLowAdr}
        onHideLowAdr={setHideLowAdr}
        sectorOptions={read.status === "ready" ? sectorOptions(read.data.boards, lookback) : []}
      />

      <Panel
        label={`${market} leaders`}
        read={read}
        skeleton={<div className="leaders-skeleton" style={{ height: 480 }} />}
      >
        {(data) => (
          <LeadersBody
            data={data}
            market={market}
            lookback={lookback}
            sort={sort}
            view={view}
            ticker={ticker}
            sector={sector}
            hideLowAdr={hideLowAdr}
            onToggleSort={toggleSort}
            onClearFilters={clearFilters}
            onOpen={openSheet}
          />
        )}
      </Panel>

      <ChartSheet target={target} onClose={() => setTarget(null)} />
    </>
  );
}

// The distinct sectors present on the active lookback's board, for the select. A
// fixed axis would offer sectors with no rows; deriving from the board keeps the
// options honest to what can actually be filtered to.
function sectorOptions(boards: Leader[], lookback: LookbackKey): string[] {
  const board = boards.find((b) => b.lookback === lookback);
  const seen = new Set<string>();
  for (const r of board?.rows ?? []) if (r.sector) seen.add(r.sector);
  return [...seen].sort();
}

function LeadersBody({
  data,
  market,
  lookback,
  sort,
  view,
  ticker,
  sector,
  hideLowAdr,
  onToggleSort,
  onClearFilters,
  onOpen,
}: {
  data: { boards: Leader[]; session: string | null };
  market: string;
  lookback: LookbackKey;
  sort: SortState;
  view: ViewKey;
  ticker: string;
  sector: string;
  hideLowAdr: boolean;
  onToggleSort: (key: SortKey) => void;
  onClearFilters: () => void;
  onOpen: (row: LeaderRow) => void;
}) {
  const board = data.boards.find((b) => b.lookback === lookback);
  const allRows = board?.rows ?? [];

  // One filter set, then one sort — the table and the grid both render this exact
  // list (spec §5.3), so the two views can never disagree.
  const rows = useMemo(() => {
    const q = ticker.trim().toUpperCase();
    const filtered = allRows.filter((r) => {
      if (q && !r.symbol.toUpperCase().includes(q)) return false;
      if (sector && r.sector !== sector) return false;
      // Hide sub-4% ADR *before the eye*, but never a name whose ADR could not be
      // computed (null) — that is not evidence of low volatility.
      if (hideLowAdr && r.adr !== null && r.adr < LOW_ADR) return false;
      return true;
    });
    return sortRows(filtered, sort);
  }, [allRows, ticker, sector, hideLowAdr, sort]);

  // The board itself is empty (no run produced leaders): a night fact, not a
  // filter, so it never apologises and carries no clear action (spec §7.4).
  if (allRows.length === 0) {
    return <NightEmpty>No leaders for {market} tonight.</NightEmpty>;
  }

  // Non-empty board, zero rows after filtering: filter-inflicted, so it carries
  // the offending chip and a clear action (spec §7.4). The default-ON ADR toggle
  // is the sharpest case — an empty a user reached without touching a control.
  if (rows.length === 0) {
    return (
      <FilterEmpty chip={filterChip(hideLowAdr, sector, ticker)} onClear={onClearFilters}>
        No leaders match the current filters.
      </FilterEmpty>
    );
  }

  const summary = `${rows.length} ${rows.length === 1 ? "name" : "names"} · ranked by ${SORT_LABELS[sort.key]} · ${market} · as of ${data.session ?? "—"}`;

  return (
    <>
      {view === "table" ? (
        <LeadersTable rows={rows} lookback={lookback} sort={sort} onToggleSort={onToggleSort} onOpen={onOpen} />
      ) : (
        <LeadersGrid rows={rows} market={market} onOpen={onOpen} />
      )}
      {/* The trailing tally counts AFTER filtering, so it reads as live, never a
          fixed 30 (spec §5.3). */}
      <p className="leaders-summary">{summary}</p>
    </>
  );
}

// The one control bar (spec §5.3): lookback segmented control, table/grid toggle,
// and the three filters. Rendered outside the Panel so it survives loading and the
// market-switch skeleton — it is view state, not a body read.
function ControlBar({
  lookback,
  onLookback,
  view,
  onView,
  ticker,
  onTicker,
  sector,
  onSector,
  hideLowAdr,
  onHideLowAdr,
  sectorOptions,
}: {
  lookback: LookbackKey;
  onLookback: (k: LookbackKey) => void;
  view: ViewKey;
  onView: (v: ViewKey) => void;
  ticker: string;
  onTicker: (v: string) => void;
  sector: string;
  onSector: (v: string) => void;
  hideLowAdr: boolean;
  onHideLowAdr: (v: boolean) => void;
  sectorOptions: string[];
}) {
  return (
    <div className="leaders-controls">
      {/* Lookback: a segmented control — exactly one active. */}
      <Segmented label="Lookback" className="lookback" options={LOOKBACKS} value={lookback} onChange={onLookback} />

      {/* Table / grid: a peer view, not an on/off (spec §5.3). */}
      <Segmented label="View" className="view" options={VIEWS} value={view} onChange={onView} />

      <label className="ticker-search">
        Ticker
        <input
          type="search"
          value={ticker}
          onChange={(e) => onTicker(e.target.value)}
          placeholder="Search ticker"
        />
      </label>

      <label className="sector-select">
        Sector
        <select value={sector} onChange={(e) => onSector(e.target.value)}>
          <option value="">All sectors</option>
          {sectorOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className="adr-toggle">
        <input type="checkbox" checked={hideLowAdr} onChange={(e) => onHideLowAdr(e.target.checked)} />
        Hide sub-4% ADR names
      </label>
    </div>
  );
}

// A segmented control — a `radiogroup` where exactly one item is active, with
// roving `tabIndex` so it takes a single tab stop. Both the lookback and the
// table/grid toggle are this same shape (spec §5.3); only their options differ.
function Segmented<K extends string>({
  label,
  className,
  options,
  value,
  onChange,
}: {
  label: string;
  className: string;
  options: readonly { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={`segmented ${className}`}>
      {options.map((opt) => {
        const active = opt.key === value;
        return (
          <button
            key={opt.key}
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            className="seg-item"
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// The `aria-sort` value for a header (spec §5.3): the active column reports its
// direction, the rest report `none`. Sorting is this screen's primary
// interaction, so the column context lives on the header, not in prose.
function ariaSort(sort: SortState, key: SortKey): "ascending" | "descending" | "none" {
  if (sort.key !== key) return "none";
  return sort.dir === "asc" ? "ascending" : "descending";
}

function LeadersTable({
  rows,
  lookback,
  sort,
  onToggleSort,
  onOpen,
}: {
  rows: LeaderRow[];
  lookback: LookbackKey;
  sort: SortState;
  onToggleSort: (key: SortKey) => void;
  onOpen: (row: LeaderRow) => void;
}) {
  const label = LOOKBACKS.find((l) => l.key === lookback)!.label;
  return (
    <table className="leaders-table" aria-label={`Leaders — top 30 by return over ${label}`}>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Ticker</th>
          <th scope="col">Sector</th>
          <SortHeader label="Return" col="return" sort={sort} onToggleSort={onToggleSort} />
          <SortHeader label="k/5" col="breadth" sort={sort} onToggleSort={onToggleSort} />
          <SortHeader label="ADR" col="adr" sort={sort} onToggleSort={onToggleSort} />
          <SortHeader label="$ Vol" col="dvol" sort={sort} onToggleSort={onToggleSort} />
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.symbol}>
            <td>{i + 1}</td>
            <td>
              <TickerButton row={r} onOpen={onOpen} />
              {r.is_new && <NewToLeaders />}
            </td>
            <td>{r.sector ?? "—"}</td>
            <td>{pct(r.raw_return)}</td>
            <td title="Lookbacks currently top-decile — a persistence count, not a quality score">
              {r.breadth}/5
            </td>
            <td>{r.adr === null ? "—" : pct(r.adr)}</td>
            <td>{r.dollar_volume === null ? "—" : formatDollarVolume(r.dollar_volume)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SortHeader({
  label,
  col,
  sort,
  onToggleSort,
}: {
  label: string;
  col: SortKey;
  sort: SortState;
  onToggleSort: (key: SortKey) => void;
}) {
  const active = sort.key === col;
  return (
    <th scope="col" aria-sort={ariaSort(sort, col)}>
      <button type="button" className="sort-button" onClick={() => onToggleSort(col)}>
        {label}
        {active && <span aria-hidden="true">{sort.dir === "asc" ? " ▲" : " ▼"}</span>}
      </button>
    </th>
  );
}

// The keyboard door into the chart sheet (spec §5.3 / §6.1): a real `<button>` on
// the ticker, on both views.
function TickerButton({ row, onOpen }: { row: LeaderRow; onOpen: (row: LeaderRow) => void }) {
  return (
    <button type="button" className="ticker" onClick={() => onOpen(row)}>
      {row.symbol}
    </button>
  );
}

// `NEW` scoped to the **active lookback** — a *ranking-movement* fact
// (`new_to_leaders`), a **different sense** from the newly-detected badge on
// Setups cards (`new_tonight`), and named apart so the two never read as the same
// thing (spec §2.4 / §5.3).
function NewToLeaders() {
  return (
    <span className="badge badge-new-to-leaders" title="New to this lookback's leaderboard since last session — a ranking move, not a new detection">
      {" "}
      NEW
    </span>
  );
}

// The grid view (spec §5.3): 3-up cards, each a lazy `MiniChart` off the shared
// 60-bar cache. Same rows, same sort, same filters as the table — only the shape
// changes. The mini is a mouse-only second door; the ticker <button> is the
// keyboard door, so the grid adds no tab stops for the decorative charts.
function LeadersGrid({
  rows,
  market,
  onOpen,
}: {
  rows: LeaderRow[];
  market: string;
  onOpen: (row: LeaderRow) => void;
}) {
  return (
    <ul className="leaders-grid" aria-label="Leaders grid">
      {rows.map((r) => (
        <li key={r.symbol} className="leader-card">
          <div className="leader-card-head">
            <TickerButton row={r} onOpen={onOpen} />
            {r.is_new && <NewToLeaders />}
          </div>
          <MiniChart market={market} symbol={r.symbol} onActivate={() => onOpen(r)} />
          <dl className="leader-card-facts">
            <div>
              <dt>Return</dt>
              <dd>{pct(r.raw_return)}</dd>
            </div>
            <div>
              <dt>k/5</dt>
              <dd>{r.breadth}/5</dd>
            </div>
            <div>
              <dt>ADR</dt>
              <dd>{r.adr === null ? "—" : pct(r.adr)}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

// The chip the filter-inflicted empty carries (spec §7.4): the ADR floor takes
// precedence — it is the default-ON control most likely to have caused an empty
// the user never asked for — then the sector, then the ticker query.
function filterChip(hideLowAdr: boolean, sector: string, ticker: string): string {
  if (hideLowAdr) return "ADR ≥ 4%";
  if (sector) return `Sector: ${sector}`;
  if (ticker.trim()) return `Ticker: ${ticker.trim()}`;
  return "Filters";
}
