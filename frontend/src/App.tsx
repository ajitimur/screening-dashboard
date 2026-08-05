import { useEffect, useState } from "react";
import { fetchRuns, type RunsResponse } from "./api/client";

const MARKETS = ["IDX", "US"] as const;
type Market = (typeof MARKETS)[number];

/**
 * The two-market tab shell (spec §5.1). Each tab reads its as-of session date
 * from the API and says so plainly when no run exists yet. The candidate list,
 * regime banner and chart panel land in later tickets against the same shell.
 */
export default function App() {
  const [market, setMarket] = useState<Market>("IDX");

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
      <Workbench market={market} />
    </main>
  );
}

function Workbench({ market }: { market: Market }) {
  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setRuns(null);
    setError(null);
    fetchRuns(market)
      .then((r) => live && setRuns(r))
      .catch((e) => live && setError(String(e)));
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
      <p className="as-of">
        As of session <time dateTime={runs.latest.session}>{runs.latest.session}</time>
      </p>
    </section>
  );
}
