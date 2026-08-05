import { useEffect, useState } from "react";
import {
  fetchRegime,
  fetchRuns,
  triggerRun,
  type RegimeResponse,
  type RunsResponse,
} from "./api/client";
import Boards from "./Boards";
import CandidateList from "./CandidateList";
import ChartPanel from "./ChartPanel";
import SectorTable from "./SectorTable";

const MARKETS = ["IDX", "US"] as const;
type Market = (typeof MARKETS)[number];

// The two screens, per spec §5: the market workbench and the boards. Market is
// the top-level axis; the screen switches under it, carrying the same market.
const SCREENS = ["Workbench", "Boards"] as const;
type Screen = (typeof SCREENS)[number];

// How often the tab re-checks a run it kicked on open (spec §7.3). A run is a
// ~9-minute pull, so a slow cadence is plenty; the poll stops as soon as the run
// lands (run_due and running both clear).
const RUN_POLL_MS = 2500;

/**
 * The two-market tab shell (spec §5.1). Each tab reads its as-of session date
 * from the API and says so plainly when no run exists yet. The candidate list,
 * regime banner and chart panel land in later tickets against the same shell;
 * the Boards screen (§5.2) is a peer tab under the same market axis.
 */
export default function App() {
  const [market, setMarket] = useState<Market>("IDX");
  const [screen, setScreen] = useState<Screen>("Workbench");

  return (
    <main>
      <h1>Qullamaggie Screening Dashboard</h1>
      <nav aria-label="market">
        {MARKETS.map((m) => (
          <button
            key={m}
            aria-current={m === market}
            disabled={m === market}
            onClick={() => setMarket(m)}
          >
            {m}
          </button>
        ))}
      </nav>
      <nav aria-label="screen">
        {SCREENS.map((s) => (
          <button
            key={s}
            aria-current={s === screen}
            disabled={s === screen}
            onClick={() => setScreen(s)}
          >
            {s}
          </button>
        ))}
      </nav>
      {screen === "Workbench" ? <Workbench market={market} /> : <Boards market={market} />}
    </main>
  );
}

function Workbench({ market }: { market: Market }) {
  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [regime, setRegime] = useState<RegimeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The one interaction: the selected candidate whose chart the panel shows
  // (spec §5.3). Cleared when the market changes — a symbol belongs to a market.
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => setSelected(null), [market]);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setRuns(null);
    setRegime(null);
    setError(null);

    // Run-on-open (spec §7.3): if the tab's last final session is missing from
    // the store, kick a run once and poll until it lands, so a forgotten night
    // is not silently stale. The served session stays the last *published* one
    // throughout — a run in progress never shows a half-written session.
    let triggered = false;
    const poll = async () => {
      let r: RunsResponse;
      try {
        r = await fetchRuns(market);
      } catch (e) {
        if (live) setError(String(e));
        return;
      }
      if (!live) return;
      setRuns(r);
      let keepPolling = r.running;
      if (r.run_due && !r.running && !triggered) {
        triggered = true;
        try {
          const t = await triggerRun(market);
          keepPolling = t.running || t.triggered;
        } catch {
          keepPolling = false; // no coordinator (503) — serve the last published
        }
      }
      if (keepPolling && live) timer = setTimeout(poll, RUN_POLL_MS);
    };
    poll();

    // The regime is its own resource endpoint (spec §7.5); the banner reads it
    // independently and never gates what the rest of the workbench shows.
    fetchRegime(market)
      .then((r) => live && setRegime(r))
      .catch(() => {});
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [market]);

  if (error) return <p role="alert">Could not reach the backend: {error}</p>;
  if (!runs) return <p>Loading {market}…</p>;

  // A run kicked on open (or a scheduled one) is in flight: show a progress
  // state above whatever the last published session was (spec §7.3).
  const progress = runs.running ? (
    <p role="status" className="run-progress">
      Running tonight's {market} pull — fetching the latest session…
    </p>
  ) : null;

  if (!runs.latest) {
    // No run has published yet: either an in-progress first run (progress state)
    // or an explicit empty state — never a fabricated date.
    return (
      <section aria-label={`${market} workbench`}>
        {progress ?? (
          <p className="empty-state">No run yet for {market}. Nothing to show tonight.</p>
        )}
      </section>
    );
  }

  // The newest run attempt is quarantined when it failed the completeness or
  // enumeration gate (spec §3.4 rules 7–8): the served `latest` session is then
  // older than the last attempt, so the tab carries a stale banner. Runs arrive
  // newest-first, so runs[0] is the last attempt.
  const newest = runs.runs[0];
  const stale = newest !== undefined && newest.status === "quarantined";

  return (
    <section aria-label={`${market} workbench`}>
      {progress}
      {stale && (
        <p role="status" className="quarantine-banner">
          Tonight's {market} run was quarantined — showing the last good session{" "}
          <time dateTime={runs.latest.session}>{runs.latest.session}</time>.
        </p>
      )}
      {regime?.session && <RegimeBanner market={market} regime={regime} />}
      <p className="as-of">
        As of session <time dateTime={runs.latest.session}>{runs.latest.session}</time>
      </p>
      {runs.universe_size !== null && (
        <p className="universe-size">
          Universe: <strong>{runs.universe_size}</strong> tradeable names
        </p>
      )}
      {/* The candidate list — the only list in the app, tonight's detections
          made readable (spec §5.1). Its own resource endpoint, sorted by star
          score descending (spec §4.7); the regime never reorders it.
          Clicking a row selects it; only the chart panel swaps (spec §5.3). */}
      <CandidateList market={market} selected={selected} onSelect={setSelected} />
      {/* The chart panel beside the list: click a row, see its chart (§5.1). */}
      <ChartPanel market={market} symbol={selected} />
      {/* The sector board reads the same as-of session (spec §4.4). The regime
          note (S7) wires in once ticket 10's /api/regime banner lands. */}
      <SectorTable market={market} />
    </section>
  );
}

/**
 * The persistent regime banner (spec §4.9). Advisory only: it carries state,
 * the sizing posture in *words*, breadth and the as-of session date, and gates
 * nothing — the candidate list is identical in all three states. Below 25 index
 * bars the state is undefined (warming up), which carries no posture. One banner
 * per market, never combined into a global verdict.
 */
function RegimeBanner({ market, regime }: { market: Market; regime: RegimeResponse }) {
  const { state, posture, breadth, session } = regime;
  const breadthPct = breadth === null ? null : `${Math.round(breadth * 100)}%`;
  return (
    <section
      className="regime-banner"
      data-state={state ?? "undefined"}
      aria-label={`${market} regime`}
    >
      {state ? (
        <>
          Regime: <strong>{state}</strong> — {posture}
        </>
      ) : (
        <>
          Regime: <strong>undefined</strong> — warming up
        </>
      )}
      {breadthPct !== null && <> · Breadth {breadthPct}</>}
      {" · as of "}
      <time dateTime={session ?? undefined}>{session}</time>
    </section>
  );
}
