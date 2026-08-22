import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Chart, MA_LINES } from "./Chart";
import { loadChart } from "./chartCache";
import type { ChartFacts, ChartResponse, ScoreRow } from "./api/client";

// The five lookbacks in order, for the decile-ranks fact (spec §4.3).
const LOOKBACKS = ["1w", "1m", "3m", "6m", "12m"] as const;

// The sheet reads the same 60-bar window the mini charts do (spec §6.4), so a
// mini already painted on the card behind the sheet makes the open a cache hit.
const SHEET_BARS = 60;

// What the caller hands the sheet to open it. The symbol is the only navigable
// fact; everything else is the **row's own data** (the chart-facts fold, spec
// §4.3) so the header, facts and breakdown paint *immediately* while the candles
// are still in flight (spec §6.3/§7.7). A screen without the fold (Leaders) may
// pass `facts`/`breakdown` null and the sheet falls back to the chart read.
export interface SheetTarget {
  symbol: string;
  market: string;
  verdict?: string | null;
  sector?: string | null;
  facts?: ChartFacts | null;
  breakdown?: ScoreRow[] | null;
  score?: number | null;
}

type ChartState =
  | { status: "loading" }
  | { status: "ready"; data: ChartResponse }
  | { status: "error" };

/**
 * The chart sheet (spec §6): one right-docked overlay, opened by click, identical
 * on all four screens — the only symbol surface in v2. `target` is the open
 * symbol (null = closed); a swap to a different symbol re-runs the open.
 *
 * Lifecycle is the caller's: it toggles `target` and closes the sheet on a tab
 * change or market switch by nulling it. The sheet owns only its own two user
 * closes — **Esc and the ×** — which return focus to the trigger. An external
 * null (a navigation) is a **teardown, not a close** (spec §8.8): it fires no
 * `onClose` and returns no focus, because focus-return was given to user acts.
 *
 * Non-modal, no backdrop, no focus trap (spec §6.2): the page stays interactive
 * behind it and Tab from the last control continues into the page rather than
 * cycling — that is what "non-modal" bought (spec §8.6). Portalled at the end of
 * the DOM; focus moves to the heading on open and every swap.
 */
export default function ChartSheet({
  target,
  onClose,
}: {
  target: SheetTarget | null;
  onClose: () => void;
}) {
  const symbol = target?.symbol ?? null;
  const market = target?.market ?? null;
  const headingRef = useRef<HTMLHeadingElement>(null);
  // The element focus returns to on a user close — captured at open time, which
  // is exactly when the ticker <button> that opened us is the active element.
  const triggerRef = useRef<HTMLElement | null>(null);

  const [chart, setChart] = useState<ChartState>({ status: "loading" });

  // Open + swap: move focus to the heading (spec §8.6). Runs whenever the symbol
  // changes to a value; a swap re-runs it because otherwise the swap detaches the
  // node focus is sitting on. A change *to* null is a teardown — no focus move,
  // no capture — so a navigation-induced close returns focus nowhere (spec §8.8).
  useEffect(() => {
    if (symbol === null) return;
    triggerRef.current = (document.activeElement as HTMLElement | null) ?? null;
    headingRef.current?.focus();
  }, [symbol]);

  // The chart read — the ONE thing the sheet blocks on, and only for the canvas.
  // Blanked on every swap so a stale canvas never sits under a new symbol.
  useEffect(() => {
    if (symbol === null || market === null) return;
    let live = true;
    setChart({ status: "loading" });
    loadChart(market, symbol, SHEET_BARS)
      .then((data) => live && setChart({ status: "ready", data }))
      .catch(() => live && setChart({ status: "error" }));
    return () => {
      live = false;
    };
  }, [market, symbol]);

  // Esc closes — a user act, so it returns focus (spec §6.2/§8.6). Bound to the
  // document because the sheet is non-modal: there is no trap to catch the key.
  useEffect(() => {
    if (symbol === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") userClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  if (target === null) return null;

  // A user-driven close (Esc, ×): return focus to the trigger, then ask the
  // parent to null the target. Focus is restored first, while the trigger is
  // unambiguously still on the page.
  function userClose() {
    triggerRef.current?.focus();
    onClose();
  }

  // The resolved facts/breakdown: the row's fold paints immediately; the chart
  // read is the fallback for a screen that had none (spec §6.3). A name with bars
  // but no detection resolves both to nothing — the degraded state (spec §6.3).
  const facts = target.facts ?? (chart.status === "ready" ? chart.data.facts : null);
  const breakdown =
    target.breakdown ??
    (chart.status === "ready" ? chart.data.setup?.breakdown ?? null : null);
  const score = target.score ?? (chart.status === "ready" ? chart.data.setup?.score ?? null : null);
  // "No base tonight" is only knowable once the read lands: until then the row
  // may still have supplied a fold, and an unresolved read is not "no base".
  const noBase = chart.status === "ready" && facts === null && (breakdown === null || breakdown.length === 0);

  return createPortal(
    <aside className="chart-sheet" aria-labelledby="chart-sheet-heading">
      {/* Header: symbol · verdict badge (neutral) · sector · × (spec §6.3). The
          heading is a polite live region and the focus target on open/swap — a
          silent full-content swap is louder than a notice (spec §8.7). */}
      <header className="chart-sheet-header">
        <h2
          id="chart-sheet-heading"
          ref={headingRef}
          tabIndex={-1}
          aria-live="polite"
          className="chart-sheet-title"
        >
          {target.symbol}
        </h2>
        {target.verdict && <span className="verdict-badge">{target.verdict}</span>}
        {target.sector && <span className="chart-sheet-sector">{target.sector}</span>}
        <button type="button" className="chart-sheet-close" onClick={userClose} aria-label={`Close ${target.symbol} chart`}>
          ×
        </button>
      </header>

      {/* Chart — never blocks the sheet (spec §7.7). It skeletons while the read
          is in flight and a failed read replaces the canvas ONLY; the facts and
          breakdown below stay readable. */}
      <div className="chart-sheet-canvas">
        {chart.status === "loading" ? (
          <div className="chart-skeleton" aria-busy="true" data-testid="chart-skeleton" />
        ) : chart.status === "error" ? (
          <p className="chart-sheet-canvas-error">Chart unavailable right now.</p>
        ) : (
          <>
            <Chart data={chart.data} height={320} />
            <MaLegend />
          </>
        )}
      </div>

      {noBase ? (
        <p className="chart-sheet-nobase">No base tonight — nothing to describe.</p>
      ) : (
        <>
          {facts && <FactsBlock facts={facts} />}
          {breakdown && breakdown.length > 0 && <Breakdown breakdown={breakdown} score={score} />}
        </>
      )}
    </aside>,
    document.body,
  );
}

// The MA legend (spec §6.3): text mapping each colour to its line, since the
// canvas is `aria-hidden` and cannot carry the mapping itself.
function MaLegend() {
  return (
    <ul className="ma-legend" aria-label="moving averages">
      {MA_LINES.map((line) => (
        <li key={line.key}>
          <span className="ma-swatch" style={{ background: line.color }} aria-hidden="true" />
          {line.label}
        </li>
      ))}
    </ul>
  );
}

/**
 * The facts block (spec §6.3): the numbers the row deliberately left off, read
 * here where the trade is decided. Identical field set to v1's chart panel.
 */
function FactsBlock({ facts }: { facts: ChartFacts }) {
  return (
    <dl aria-label="facts" className="facts">
      <div>
        <dt>Trigger</dt>
        <dd>{facts.trigger.toFixed(2)}</dd>
      </div>
      <div>
        <dt>Stop width ÷ ADR</dt>
        <dd>{facts.stopw_adr.toFixed(2)}×</dd>
      </div>
      <div>
        <dt>Distance to trigger</dt>
        <dd>{facts.dist_adr.toFixed(2)}×</dd>
      </div>
      <div>
        <dt>ADR</dt>
        <dd>{(facts.adr * 100).toFixed(2)}%</dd>
      </div>
      <div>
        <dt>Base length</dt>
        <dd>{facts.base_len} bars</dd>
      </div>
      <div>
        <dt>Dollar volume</dt>
        <dd>{facts.dollar_volume === null ? "—" : formatDollarVolume(facts.dollar_volume)}</dd>
      </div>
      <div>
        <dt>Decile ranks</dt>
        <dd>{formatRanks(facts.decile_ranks)}</dd>
      </div>
      <div>
        <dt>Sector</dt>
        <dd>{facts.sector ?? "—"}</dd>
      </div>
    </dl>
  );
}

/**
 * The eight-row §4.7 breakdown, LAST (spec §6.3): a narrow column has no room
 * beside the chart and it is audit material consulted *after* the chart. It
 * renders from the candidate row's `breakdown`, so it paints while candles are
 * still in flight — the arithmetic that reconstructs the star score from the
 * per-dimension hits, because a sort key you cannot audit is one you will not
 * trust.
 */
/**
 * What one dimension's "Scored" cell says. Three cases, and the middle one only
 * exists because rubric v3 grades a dimension (#154): a row can earn *part* of its
 * weight, and a tick would overstate it while a dash would deny it.
 */
function scoredMark(d: ScoreRow): string {
  if (d.points === 0) return "—"; // missed, or a ×0 dimension that can earn nothing
  if (d.points === d.weight) return "✓"; // earned everything it could
  return `+${d.points}`; // graded: part of the weight
}

function Breakdown({ breakdown, score }: { breakdown: ScoreRow[]; score: number | null }) {
  // Points come off the row, not from `hit × weight`. Since rubric v3 one
  // dimension is *graded* — it earns part of its weight on a banded value — so
  // re-deriving the total here would need a copy of the server's band table and
  // would silently disagree with the star the row was sorted by (#154).
  const points = breakdown.reduce((sum, d) => sum + d.points, 0);
  // The ceiling is the sum of the weights, read off the breakdown itself rather
  // than hard-coded — so the ×0 Base length row (PRD #138) drops it to 9 without
  // a second place to keep in sync.
  const ceiling = breakdown.reduce((sum, d) => sum + d.weight, 0);
  return (
    <table aria-label="score breakdown" className="breakdown">
      <thead>
        <tr>
          <th scope="col">Dimension</th>
          <th scope="col">Weight</th>
          <th scope="col">Scored</th>
        </tr>
      </thead>
      <tbody>
        {breakdown.map((d) => (
          <tr key={d.dimension} className={d.points > 0 ? "hit" : "miss"}>
            <td>
              {d.dimension}
              {/* A graded dimension shows the value it was graded on, so a
                  partial score reads as a measurement rather than a mystery. */}
              {d.value !== null && d.value !== undefined && (
                <span className="graded-value"> {d.value.toFixed(2)} ADR</span>
              )}
            </td>
            <td>×{d.weight}</td>
            <td>{scoredMark(d)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={2}>{points} / {ceiling} points</td>
          <td>{score === null ? "—" : `→ ${score}★`}</td>
        </tr>
      </tfoot>
    </table>
  );
}

// Compact dollar volume, e.g. "$1.2M" — the §4.1 median-20d liquidity number.
function formatDollarVolume(value: number): string {
  return `$${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

// The five decile ranks as percentiles, in lookback order, e.g. "1m 95 · 3m 90".
// A lookback the name is not ranked in (a recent listing) is simply omitted.
function formatRanks(ranks: Record<string, number>): string {
  const parts = LOOKBACKS.filter((lb) => lb in ranks).map(
    (lb) => `${lb} ${Math.round(ranks[lb] * 100)}`,
  );
  return parts.length === 0 ? "—" : parts.join(" · ");
}
