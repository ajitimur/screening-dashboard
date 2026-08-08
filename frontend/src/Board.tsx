import { useEffect, useState, type ReactNode } from "react";
import {
  fetchCandidates,
  fetchLeaders,
  fetchSectors,
  type Candidate,
  type CandidatesResponse,
  type LeaderRow,
  type LeadersResponse,
  type SectorStrength,
  type SectorsResponse,
} from "./api/client";
import { NightEmpty, useBodyRead, type BodyRead } from "./Panel";
import ChartSheet, { type SheetTarget } from "./ChartSheet";

// ── The Board (spec §5.1) ────────────────────────────────────────────────────
//
// The landing screen, and the one v1 lacked. Its job is to **cut, not stack** —
// the stated reason v1's Workbench failed. Layout is `1fr + 384px`: heroes and
// the leaders strip in the left column, the rotation rail on the right. Every
// number is a *composition* of the existing thin reads (spec §4.1: "The Board
// needs no new endpoint") — candidates for the heroes and the funnel's detected
// count, leaders for the strip, sectors for the rail.

// The hero cut (spec §5.1): the `≥3.5★` subset of `detected`, capped at 4, sorted
// stars descending with `stopw_adr` ascending as the tie-break, and **no
// placeholder slots** — two cards then the next section is honest. The cut is
// `≥3.5`, not `>3.5`: on half-star granularity `>3.5` means 4.0+, which would
// collapse IDX to one card on the market that is already sparsest (spec §11.1).
const HERO_MIN = 3.5;
const HERO_CAP = 4;

// The leaders strip (spec §5.1): 1-month only, heroes included (no dedup). The
// strip stretches to the bottom of the left column and scrolls internally, so
// what keeps it off Leaders' turf is lookback count (one vs five), not content.
const STRIP_LOOKBACK = "1m";

// The rotation rail (spec §5.1): the top-5 sectors by shape differential, drawn
// as centre-anchored diverging bars. The panel is named for *behaviour*, not the
// artifact, so it survives phase 2 (when the RRG map appends above) unchanged.
const RAIL_TOP = 5;

// The stop-width bar and the rotation bars both encode a continuous magnitude as
// a fraction of a nominal ceiling — inline `style` widths, the one case no class
// can enumerate (spec §3.2). Past the ceiling the bar simply pins full.
const STOP_BAR_MAX = 3; // ×ADR; ~92% of names are wider than 1×ADR (spec §4.6)
const ROTATION_BAR_MAX = 0.3; // shape differential, as a fraction

// GECS sector → the sector-scale token (spec §3.2). Ten hues for eleven sectors:
// Real Estate (and any unanticipated label) falls back to the non-text fill, the
// "existing fallback branch" a static map needs. On the Board the swatch is
// wayfinding only — the sector is named in adjacent text — so it is exempt from
// the 1.4.11 contrast floor (spec §8.4) and the fallback is harmless.
const SECTOR_VAR: Record<string, string> = {
  Technology: "--color-sector-technology",
  "Financial Services": "--color-sector-financials",
  Industrials: "--color-sector-industrials",
  "Communication Services": "--color-sector-communication",
  "Consumer Cyclical": "--color-sector-consumer-cyclical",
  Healthcare: "--color-sector-healthcare",
  Utilities: "--color-sector-utilities",
  Energy: "--color-sector-energy",
  "Basic Materials": "--color-sector-materials",
  "Consumer Defensive": "--color-sector-defensive",
};

function sectorColor(sector: string | null): string {
  const v = sector ? SECTOR_VAR[sector] : undefined;
  return `var(${v ?? "--color-fill-faint"})`;
}

function heroCut(candidates: Candidate[]): Candidate[] {
  return candidates
    .filter((c) => c.score >= HERO_MIN)
    .sort((a, b) => b.score - a.score || a.stopw_adr - b.stopw_adr)
    .slice(0, HERO_CAP);
}

// A signed percentage-point value, e.g. "+12pp" / "−5pp" — the sign is carried in
// text so the diverging rotation bar never leans on hue alone (spec §8.4/§1.4.1).
function signedPct(value: number): string {
  const pp = Math.round(value * 100);
  return `${pp > 0 ? "+" : pp < 0 ? "−" : ""}${Math.abs(pp)}pp`;
}

// A signed return, e.g. "+42.0%" — the leaders strip's 1M column.
function signedReturn(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value * 100).toFixed(1)}%`;
}

const listedFmt = new Intl.NumberFormat("en");

/**
 * The Board screen. Owns the one chart sheet its cards and strip open (spec §6):
 * `selected` is the open target, nulled on a user close, on a re-click of the same
 * ticker (toggle), and on a market switch (the entity-state reset, spec §3.4).
 * While the sheet is open the rail collapses and the sheet takes its place, so the
 * hero grid keeps its two columns (spec §5.1) rather than reflowing on every open.
 */
export default function Board({
  market,
  universeSize,
  navigate,
}: {
  market: string;
  universeSize: number | null;
  navigate: (patch: { tab?: string; sector?: string | null }) => void;
}) {
  const candidates = useBodyRead<CandidatesResponse>(market, fetchCandidates);
  const leaders = useBodyRead<LeadersResponse>(market, fetchLeaders);
  const sectors = useBodyRead<SectorsResponse>(market, fetchSectors);

  const [selected, setSelected] = useState<SheetTarget | null>(null);
  const sheetOpen = selected !== null;

  // A market switch resets entity-naming state (spec §3.4): the open symbol is a
  // named entity, so the sheet closes. View-shape state (there is none on the
  // Board) would survive.
  useEffect(() => {
    setSelected(null);
  }, [market]);

  // Open, or toggle closed if the same ticker is clicked again (spec §6.2). The
  // hero card carries its fold (breakdown + score) so the sheet's breakdown paints
  // immediately; a candidate has no `base_len`, so `facts` is left to the chart
  // read (spec §6.3). The leaders strip carries no fold — the sheet reads it all.
  function openTarget(next: SheetTarget) {
    setSelected((prev) => (prev?.symbol === next.symbol ? null : next));
  }

  function openCandidate(c: Candidate) {
    openTarget({
      symbol: c.symbol,
      market,
      verdict: c.verdict ?? null,
      sector: c.sector,
      breakdown: c.breakdown,
      score: c.score,
    });
  }

  function openLeader(r: LeaderRow) {
    openTarget({ symbol: r.symbol, market, sector: r.sector });
  }

  const selectedSymbol = selected?.symbol ?? null;

  return (
    <>
      <div className={`board-grid${sheetOpen ? " board-grid--sheet-open" : ""}`}>
        <div className="board-left">
          <HeroPanel
            read={candidates}
            universeSize={universeSize}
            selectedSymbol={selectedSymbol}
            onOpen={openCandidate}
            onViewCharts={() => navigate({ tab: "setups" })}
          />
          <LeadersStripPanel
            read={leaders}
            selectedSymbol={selectedSymbol}
            onOpen={openLeader}
            onSeeAll={() => navigate({ tab: "leaders" })}
          />
        </div>

        {/* The rail collapses while the sheet is open (spec §5.1): the ~540px
            sheet takes its place, so the hero grid keeps its two columns rather
            than reflowing on every open — a chart is opened constantly. */}
        {!sheetOpen && (
          <div className="board-rail">
            <RotationPanel read={sectors} onOpenSector={(s) => navigate({ tab: "sectors", sector: s })} />
          </div>
        )}
      </div>

      <ChartSheet target={selected} onClose={() => setSelected(null)} />
    </>
  );
}

/**
 * A Board panel: a `<section>` named by its `<h2>` (spec §8.5), whose heading and
 * head furniture (the funnel line, the "See all →" jump) persist across every read
 * state so the navigation structure never blinks. The body mirrors the §7 matrix —
 * a static skeleton while busy, a POLITE notice on failure (never an alert, so N
 * dead panels do not shout N times), the children when ready.
 */
function BoardPanel<T>({
  id,
  title,
  head,
  read,
  skeleton,
  children,
}: {
  id: string;
  title: string;
  head?: ReactNode;
  read: BodyRead<T>;
  skeleton: ReactNode;
  children: (data: T) => ReactNode;
}) {
  const busy = read.status === "loading" || read.status === "switching";
  return (
    <section className="board-panel" aria-labelledby={id} aria-busy={busy || undefined}>
      <div className="board-panel-head">
        <h2 id={id}>{title}</h2>
        {head}
      </div>
      {read.status === "error" ? (
        <p role="status" className="panel-notice">
          {title} is unavailable right now.
        </p>
      ) : busy ? (
        skeleton
      ) : (
        children(read.data)
      )}
    </section>
  );
}

function HeroPanel({
  read,
  universeSize,
  selectedSymbol,
  onOpen,
  onViewCharts,
}: {
  read: BodyRead<CandidatesResponse>;
  universeSize: number | null;
  selectedSymbol: string | null;
  onOpen: (c: Candidate) => void;
  onViewCharts: () => void;
}) {
  return (
    <BoardPanel
      id="board-heroes-h"
      title="Tonight's setups"
      head={
        <button type="button" className="board-jump" onClick={onViewCharts}>
          view charts →
        </button>
      }
      read={read}
      skeleton={<div className="hero-grid-skeleton" data-testid="hero-skeleton" />}
    >
      {(data) => {
        const heroes = heroCut(data.candidates);
        return (
          <>
            {/* The universe funnel — one line under the hero section header, not a
                stat panel and not a rail tile (spec §5.1). It answers "is tonight
                thin, or is the pipeline broken?", the same question a two-card
                night raises, so it belongs beside the cards. */}
            <p className="board-funnel">
              {universeSize !== null && <>{listedFmt.format(universeSize)} listed · </>}
              {data.candidates.length} detected
            </p>
            {heroes.length === 0 ? (
              // A quiet night is a FACT, not unfilled capacity — no placeholder
              // slots (spec §5.1/§7.4). The prose names the bar and never apologises.
              <NightEmpty>No name cleared the ≥3.5★ bar tonight.</NightEmpty>
            ) : (
              <div className="hero-grid">
                {heroes.map((c) => (
                  <HeroCard
                    key={c.symbol}
                    candidate={c}
                    active={c.symbol === selectedSymbol}
                    onOpen={onOpen}
                  />
                ))}
              </div>
            )}
          </>
        );
      }}
    </BoardPanel>
  );
}

/**
 * A hero card (spec §5.1): `ticker · stars · NEW · sector` / `TRIGGER · STOP ·
 * DIST` / the stop-width bar labelled with its ADR multiple. Chart-less — mini
 * charts live on Setups cards and the Leaders grid, nowhere else (spec §6.4). An
 * `<article>` named by the ticker, its stats a `<dl>` so a screen reader pairs
 * each label with its value (spec §8.5). The source card stays visibly lit while
 * its sheet is open.
 */
function HeroCard({
  candidate: c,
  active,
  onOpen,
}: {
  candidate: Candidate;
  active: boolean;
  onOpen: (c: Candidate) => void;
}) {
  return (
    <article className={`hero-card${active ? " is-active" : ""}`} aria-label={c.symbol}>
      <div className="hero-card-head">
        <button
          type="button"
          className="ticker"
          aria-current={active || undefined}
          onClick={() => onOpen(c)}
        >
          {c.symbol}
        </button>
        <span className="stars" aria-label={`${c.score.toFixed(1)} stars`}>
          {c.score.toFixed(1)}★
        </span>
        {/* NEW is a badge where the name already appears, and nowhere else — the
            standalone "New tonight" panel is killed (spec §5.1). */}
        {c.new_tonight && <span className="badge-new">NEW</span>}
        <SectorChip sector={c.sector} />
      </div>
      <dl className="hero-stats">
        <div>
          <dt>Trigger</dt>
          <dd>{c.trigger_price.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Stop</dt>
          <dd>{c.stop_price.toFixed(2)}</dd>
        </div>
        {/* DIST is the permanent third stat, not a stand-in for MOVE (spec §5.1):
            it answers how far away this is tonight, which trigger and stop do not. */}
        <div>
          <dt>Dist</dt>
          <dd>{c.dist_adr.toFixed(2)}×</dd>
        </div>
      </dl>
      <StopWidthBar stopw={c.stopw_adr} />
    </article>
  );
}

// The stop-width bar (spec §5.1/§5.0): the fill is green/amber/red by width —
// "colouring a number by what it is carries no recommendation" — and the label
// carries the ×ADR multiple in text, so colour is never the sole carrier.
function StopWidthBar({ stopw }: { stopw: number }) {
  const tier = stopw <= 1 ? "tight" : stopw <= 2 ? "mid" : "wide";
  const width = Math.min(stopw / STOP_BAR_MAX, 1) * 100;
  return (
    <div className="stop-bar-row">
      <span className="stop-bar-track" aria-hidden="true">
        <span className={`stop-bar-fill stop-bar-fill--${tier}`} style={{ width: `${width}%` }} />
      </span>
      <span className="stop-bar-label">stop {stopw.toFixed(1)}×ADR</span>
    </div>
  );
}

function SectorChip({ sector }: { sector: string | null }) {
  return (
    <span className="sector-chip">
      <span className="sector-swatch" style={{ background: sectorColor(sector) }} aria-hidden="true" />
      {sector ?? "—"}
    </span>
  );
}

function LeadersStripPanel({
  read,
  selectedSymbol,
  onOpen,
  onSeeAll,
}: {
  read: BodyRead<LeadersResponse>;
  selectedSymbol: string | null;
  onOpen: (r: LeaderRow) => void;
  onSeeAll: () => void;
}) {
  return (
    <BoardPanel
      id="board-strip-h"
      title="Momentum leaders"
      head={
        <button type="button" className="board-jump" onClick={onSeeAll}>
          See all →
        </button>
      }
      read={read}
      skeleton={<div className="leaders-strip-skeleton" data-testid="strip-skeleton" />}
    >
      {(data) => {
        // 1-month only (spec §5.1): the strip is a straight top-10 momentum list,
        // heroes included and no dedup. Leaders owes no de-duplication back.
        const board = data.boards.find((b) => b.lookback === STRIP_LOOKBACK);
        const rows = board?.rows ?? [];
        if (rows.length === 0) {
          return <NightEmpty>No 1-month leaders ranked yet tonight.</NightEmpty>;
        }
        return (
          <div className="leaders-strip-scroll">
            <table className="leaders-strip">
              <thead>
                <tr>
                  <th scope="col">Ticker</th>
                  <th scope="col">Sector</th>
                  <th scope="col">1M</th>
                  <th scope="col">k/5</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol} aria-selected={r.symbol === selectedSymbol || undefined}>
                    <th scope="row">
                      <button
                        type="button"
                        className="ticker"
                        aria-current={r.symbol === selectedSymbol || undefined}
                        onClick={() => onOpen(r)}
                      >
                        {r.symbol}
                      </button>
                    </th>
                    <td>{r.sector ?? "—"}</td>
                    <td className="strip-return">{signedReturn(r.raw_return)}</td>
                    <td className="strip-breadth">{r.breadth}/5</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }}
    </BoardPanel>
  );
}

function RotationPanel({
  read,
  onOpenSector,
}: {
  read: BodyRead<SectorsResponse>;
  onOpenSector: (sector: string) => void;
}) {
  return (
    <BoardPanel
      id="board-rotation-h"
      title="Where money is rotating"
      read={read}
      skeleton={<div className="rotation-skeleton" data-testid="rotation-skeleton" />}
    >
      {(data) => {
        const top = [...data.sectors]
          .sort((a, b) => b.shape_differential - a.shape_differential)
          .slice(0, RAIL_TOP);
        return (
          <ul className="rotation-list">
            {top.map((s) => (
              <RotationBar key={s.sector} sector={s} onOpen={() => onOpenSector(s.sector)} />
            ))}
          </ul>
        );
      }}
    </BoardPanel>
  );
}

// A centre-anchored diverging bar (spec §5.1/§8.4): left negative, right positive.
// A bar growing away from the centre says what the panel is named for, where a
// one-sided two-colour bar would make the reader learn a legend. The signed value
// text carries the sign, so the meaning survives without colour (spec §1.4.1).
function RotationBar({ sector, onOpen }: { sector: SectorStrength; onOpen: () => void }) {
  const positive = sector.shape_differential >= 0;
  const magnitude = Math.min(Math.abs(sector.shape_differential) / ROTATION_BAR_MAX, 1) * 50;
  return (
    <li>
      <button type="button" className="rotation-bar-btn" onClick={onOpen}>
        <span className="rotation-name">{sector.sector}</span>
        <span className="rotation-track" aria-hidden="true">
          <span
            className={`rotation-fill rotation-fill--${positive ? "pos" : "neg"}`}
            style={
              positive
                ? { left: "50%", width: `${magnitude}%`, background: sectorColor(sector.sector) }
                : { right: "50%", width: `${magnitude}%`, background: "var(--color-fill-faint)" }
            }
          />
        </span>
        <span className="rotation-value">{signedPct(sector.shape_differential)}</span>
      </button>
    </li>
  );
}
