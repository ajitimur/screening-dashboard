import { useEffect, useState } from "react";
import {
  fetchCandidates,
  type Candidate,
  type CandidatesResponse,
} from "./api/client";

// §7's 1×ADR affordability cap: the backend flags the sub-1×ADR minority and the
// column highlights it. About 92% of rows sit above it (median 1.28×), so a flag
// on the failures would fire on nearly every row — the useful form is the inverse
// (spec §4.6). The value lives on the row (`affordable`); this is copy only.
function stopWidth(c: Candidate): string {
  return `${c.stopw_adr.toFixed(2)}×`;
}

function distance(c: Candidate): string {
  return `${c.dist_adr.toFixed(2)}×`;
}

/**
 * The candidate list — tonight's detections as the five-column list of the market
 * workbench (spec §5.1 / ticket 38): ticker · star score · distance to trigger ·
 * stop width in ADR · industry · k/5 breadth.
 *
 * Two properties are load-bearing:
 * - The **star score is a placeholder** (`—`) until the rubric lands (ticket 39),
 *   so the list is **ordered by ticker** and says so, rather than inventing a
 *   temporary sort — sorting by distance to trigger was explicitly rejected
 *   (it puts a 2★ barcode above a 5★ base).
 * - The **stop column never filters**. It highlights the affordable sub-1×ADR
 *   minority instead of marking the ~92% unaffordable majority (spec §4.6).
 *
 * The row decides whether to open the chart; the chart decides whether to trade —
 * so ADR, dollar volume, base length, the decile ranks and sector live in the
 * chart panel, not here.
 */
export default function CandidateList({ market }: { market: string }) {
  const [data, setData] = useState<CandidatesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    fetchCandidates(market)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [market]);

  if (error)
    return (
      <p role="alert" className="candidate-error">
        Could not load candidates: {error}
      </p>
    );
  if (!data) return <p>Loading candidates…</p>;

  if (data.candidates.length === 0)
    return (
      <p className="candidate-empty">
        No candidates tonight — no name is sitting in a valid base.
      </p>
    );

  return (
    <section aria-label={`${market} candidates`} className="candidate-list">
      <h2>Candidates</h2>
      {data.ordered_by === "ticker" && (
        <p role="note" className="sort-note">
          Ordered by ticker — the star score sort is not yet live.
        </p>
      )}
      <table aria-label={`${market} candidates`}>
        <thead>
          <tr>
            <th scope="col">Ticker</th>
            <th scope="col">Star score</th>
            <th scope="col">Distance to trigger</th>
            <th scope="col">Stop width ÷ 1×ADR</th>
            <th scope="col">Industry</th>
            <th scope="col">k/5</th>
          </tr>
        </thead>
        <tbody>
          {data.candidates.map((c) => (
            <tr key={c.symbol}>
              <th scope="row">{c.symbol}</th>
              {/* Placeholder until the rubric lands — never a fabricated number. */}
              <td className="score">{c.score === null ? "—" : c.score.toFixed(1)}</td>
              <td className="distance">{distance(c)}</td>
              <td className={c.affordable ? "stop affordable" : "stop"}>
                {stopWidth(c)}
              </td>
              <td className="industry">{c.industry ?? "—"}</td>
              <td className="breadth">{c.breadth}/5</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
