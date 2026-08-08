import { useEffect, useRef, useState } from "react";
import ChartSheet, { type SheetTarget } from "./ChartSheet";
import MiniChart from "./MiniChart";
import { NightEmpty, Panel, useBodyRead } from "./Panel";
import { fetchCandidates, type Candidate } from "./api/client";

// The render cap (spec §5.2): the grid draws 60 cards, then a client-side
// `show N more` appends the next 60. 60 sits comfortably above every phase-1
// population and only ever engages against phase-2 `forming`; a labelled button
// — never infinite scroll — keeps the total honest and does not fight the minis'
// `IntersectionObserver` loading.
const RENDER_CAP = 60;

// The stop-width bar saturates at 3×ADR (spec §4.6): a wider stop is off the
// tradeable end of the scale, so the bar simply pins full. The quantity is
// `stopw_adr`; the bar is labelled `stop N×ADR` and `risk_adr` is refused.
const STOPW_FULL = 3;

// Both ADR columns read as a multiple of one average daily range, e.g. "1.28×".
function adrMultiple(value: number): string {
  return `${value.toFixed(2)}×`;
}

/**
 * The Setups screen (spec §5.2) — **the grid *is* the screen**: no rail, no
 * strip, no composite. It is the chart-looking screen you arrive at from the
 * Board; a card grid, **never a table**, so the mini chart that is its whole
 * reason to exist survives.
 *
 * Phase 1 renders exactly the `detected` population (the candidate list) and is
 * complete in itself — **no verdict control, no empty axis**. Two controls and no
 * sort: ticker search and a sector filter, both dismissible chips when carried
 * in. The order is fixed — **`score` desc, `stopw_adr` asc** — identical to the
 * Board's hero cut, so a sort selector (which would invite re-ranking a rubric
 * ruled out of scope) has no place.
 *
 * The header always reports the **true filtered total**, never the rendered
 * count; the grid caps at 60 with a `show N more`. Opening the sheet reflows the
 * grid to two columns and the clicked card keeps an active outline so it survives
 * the reflow and you do not lose your place.
 *
 * `carriedSector` is a sector carried in from the Sectors drill-down (spec §5.6):
 * it seeds the sector filter and renders as a dismissible chip. It survives tab
 * changes until dismissed or until the market changes; a market switch resets it
 * along with the rest of this screen's entity state (spec §3.4).
 */
export default function Setups({
  market,
  carriedSector,
  onClearCarried,
}: {
  market: string;
  carriedSector?: string | null;
  onClearCarried?: () => void;
}) {
  const read = useBodyRead(market, fetchCandidates);

  // Entity-naming state, reset on a market switch (spec §3.4): the ticker query,
  // the carried sector chip, the open sheet and the render cap. View-shape state
  // (there is none here — the order is fixed) would survive.
  const [ticker, setTicker] = useState("");
  const [sector, setSector] = useState<string | null>(carriedSector ?? null);
  const [carried, setCarried] = useState<boolean>(carriedSector != null);
  const [cap, setCap] = useState(RENDER_CAP);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);

  // Reset entity state on a market SWITCH only — never on the first mount, which
  // would wipe the carried sector before it is ever shown. The seeded state above
  // is the cold-open truth; this effect fires only once `market` actually changes.
  const prevMarket = useRef(market);
  useEffect(() => {
    if (prevMarket.current === market) return;
    prevMarket.current = market;
    setTicker("");
    setSector(null);
    setCarried(false);
    setCap(RENDER_CAP);
    setSheet(null);
  }, [market]);

  function clearSector() {
    setSector(null);
    setCarried(false);
    onClearCarried?.();
  }

  function openSheet(c: Candidate) {
    // The row's fold (spec §4.3/§6.3): verdict, sector, breakdown and score paint
    // the sheet immediately; the facts block awaits the chart read because the
    // candidate row carries no `base_len`. The symbol is the only navigable fact.
    setSheet({
      symbol: c.symbol,
      market,
      verdict: c.verdict,
      sector: c.sector,
      breakdown: c.breakdown,
      score: c.score,
    });
  }

  return (
    <>
      <Panel
        label={`${market} setups`}
        read={read}
        skeleton={<div className="setups-skeleton" style={{ minHeight: 320 }} />}
      >
        {(data) => {
          const all = data.candidates;
          // Phase 1 renders exactly `detected` (the candidate list) — no verdict
          // control filters it. Only the two live filters cut the population.
          const filtered = all.filter(
            (c) =>
              (sector === null || c.sector === sector) &&
              (ticker === "" ||
                c.symbol.toLowerCase().includes(ticker.trim().toLowerCase())),
          );
          // Fixed order — `score` desc, `stopw_adr` asc (spec §5.2), the Board's
          // hero cut, so both screens agree on what "better" means. No sort UI.
          const ordered = [...filtered].sort(
            (a, b) => b.score - a.score || a.stopw_adr - b.stopw_adr,
          );
          // The header reports the TRUE filtered total, never the rendered count
          // — that is what discharges the row-count question (spec §5.2).
          const total = ordered.length;
          const shown = ordered.slice(0, cap);
          const more = total - shown.length;

          // The sector options are the sectors actually present tonight, so the
          // filter never offers an empty cut.
          const sectors = Array.from(
            new Set(all.map((c) => c.sector).filter((s): s is string => s !== null)),
          ).sort();

          const filtersActive = ticker !== "" || sector !== null;

          return (
            <div className="setups">
              <div className="setups-controls">
                <input
                  type="search"
                  className="setups-search"
                  aria-label="Search ticker"
                  placeholder="Ticker…"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                />
                {/* The sector filter renders as a dismissible chip when carried
                    in from the Sectors drill-down (spec §5.6/§5.2); otherwise it
                    is the plain select. Either way it cuts the same population. */}
                {carried && sector !== null ? (
                  <span className="chip carried-sector">
                    Sector: {sector}
                    <button
                      type="button"
                      className="chip-clear"
                      aria-label="Clear sector filter"
                      onClick={clearSector}
                    >
                      ×
                    </button>
                  </span>
                ) : (
                  <select
                    className="setups-sector"
                    aria-label="Filter by sector"
                    value={sector ?? ""}
                    onChange={(e) => setSector(e.target.value || null)}
                  >
                    <option value="">All sectors</option>
                    {sectors.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                )}
                <p className="setups-count">
                  {total} {total === 1 ? "setup" : "setups"} · as of{" "}
                  <time dateTime={data.session ?? undefined}>{data.session}</time>
                </p>
              </div>

              {total === 0 ? (
                filtersActive ? (
                  // A recoverable, filter-inflicted empty (spec §7.4): the click
                  // that un-empties it is on screen.
                  <div className="empty-filter">
                    <p>No detected name matches the current filter.</p>
                    <button
                      type="button"
                      className="chip-clear"
                      onClick={() => {
                        setTicker("");
                        clearSector();
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                ) : (
                  // A thin night gets no special copy — the header count is the
                  // whole explanation (spec §5.2). A plain fact, never an apology.
                  <NightEmpty>No names cleared every gate tonight.</NightEmpty>
                )
              ) : (
                <>
                  {/* The grid reflows by card width, never a fixed column count
                      (spec §5.2). Under the sheet it drops to two columns and the
                      clicked card keeps its outline — both driven off
                      `data-sheet-open` since jsdom computes no CSS. */}
                  <div
                    className="setups-grid"
                    data-sheet-open={sheet !== null || undefined}
                  >
                    {shown.map((c) => (
                      <SetupCard
                        key={c.symbol}
                        candidate={c}
                        market={market}
                        active={sheet?.symbol === c.symbol}
                        onOpen={() => openSheet(c)}
                      />
                    ))}
                  </div>
                  {more > 0 && (
                    <button
                      type="button"
                      className="setups-more"
                      onClick={() => setCap((n) => n + RENDER_CAP)}
                    >
                      Show {more} more
                    </button>
                  )}
                </>
              )}
            </div>
          );
        }}
      </Panel>

      {/* The sheet lives outside the Panel so it persists across read states; a
          market switch nulls it through the reset effect above (a teardown, not a
          user close — no focus return, spec §8.8). */}
      <ChartSheet target={sheet} onClose={() => setSheet(null)} />
    </>
  );
}

/**
 * One Setups card (spec §5.2) — the Board card's anatomy plus the mini chart, so
 * a name looks the same wherever you meet it:
 *
 *   ticker · stars · NEW · sector
 *   TRIGGER · STOP · DIST
 *   [ mini chart ]
 *   [ stop-width bar ]  stop N×ADR
 *
 * It is an `<article>` **named by its ticker** with the three stats as a
 * description list — sibling spans would read as unrelated strings. The ticker is
 * a `<button>` (the keyboard door to the sheet); the mini chart is a second,
 * mouse-only door to the same sheet.
 */
function SetupCard({
  candidate: c,
  market,
  active,
  onOpen,
}: {
  candidate: Candidate;
  market: string;
  active: boolean;
  onOpen: () => void;
}) {
  const headingId = `setup-${c.symbol}`;
  // Saturate the bar at 3×ADR; colour never carries the meaning — the label does
  // (spec §8.9). `affordable` (sub-1×ADR) is the one tint worth keeping.
  const fill = Math.min(c.stopw_adr / STOPW_FULL, 1) * 100;
  return (
    <article
      className="setup-card"
      aria-labelledby={headingId}
      data-active={active || undefined}
    >
      <header className="setup-card-head">
        <button
          type="button"
          id={headingId}
          className="ticker-select"
          aria-current={active}
          onClick={onOpen}
        >
          {c.symbol}
        </button>
        <span className="stars">{c.score.toFixed(1)}★</span>
        {c.new_tonight && <span className="new-badge">NEW</span>}
        {c.sector && <span className="sector-chip">{c.sector}</span>}
      </header>

      <dl className="setup-stats">
        <div>
          <dt>Trigger</dt>
          <dd>{c.trigger_price.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Stop</dt>
          <dd>{c.stop_price.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Distance to trigger</dt>
          <dd>{adrMultiple(c.dist_adr)}</dd>
        </div>
      </dl>

      <MiniChart market={market} symbol={c.symbol} onActivate={onOpen} />

      <div className="stopw-bar-row">
        <div className="stopw-bar" aria-hidden="true">
          <span
            className={c.affordable ? "stopw-bar-fill affordable" : "stopw-bar-fill"}
            style={{ width: `${fill}%` }}
          />
        </div>
        <span className="stopw-bar-label">stop {adrMultiple(c.stopw_adr)}ADR</span>
      </div>
    </article>
  );
}
