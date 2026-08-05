import { useEffect, useState } from "react";
import {
  fetchRegime,
  fetchRuns,
  type RegimeResponse,
  type RunsResponse,
} from "./api/client";
import Boards from "./Boards";
import CandidateList from "./CandidateList";
import SectorTable from "./SectorTable";

const MARKETS = ["IDX", "US"] as const;
type Market = (typeof MARKETS)[number];

// The two screens, per spec §5: the market workbench and the boards. Market is
// the top-level axis; the screen switches under it, carrying the same market.
const SCREENS = ["Workbench", "Boards"] as const;
type Screen = (typeof SCREENS)[number];

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

  useEffect(() => {
    let live = true;
    setRuns(null);
    setRegime(null);
    setError(null);
    fetchRuns(market)
      .then((r) => live && setRuns(r))
      .catch((e) => live && setError(String(e)));
    // The regime is its own resource endpoint (spec §7.5); the banner reads it
    // independently and never gates what the rest of the workbench shows.
    fetchRegime(market)
      .then((r) => live && setRegime(r))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [market]);

  if (error) return <p role="alert">Could not reach the backend: {error}</p>;
  if (!runs) return <p>Loading {market}…</p>;

  if (!runs.latest) {
    // Explicit empty state — no run has published for this market yet.
    return (
      <section aria-label={`${market} workbench`}>
        <p className="empty-state">No run yet for {market}. Nothing to show tonight.</p>
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
          score descending (spec §4.7); the regime never reorders it. */}
      <CandidateList market={market} />
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
