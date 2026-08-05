import { useEffect, useMemo, useState } from "react";
import {
  fetchSectors,
  type SectorStrength,
  type SectorsResponse,
} from "./api/client";

// The five ranking lookbacks, shortest first (spec §4.3). The share columns.
const LOOKBACKS = ["1w", "1m", "3m", "6m", "12m"] as const;

// The regime states that carry the relative-strength-through-a-decline note
// (spec §4.4 S7 / ticket 10). Advisory copy, never computation.
type Regime = "FRIENDLY" | "CHOPPY" | "HOSTILE";

// The two sortable rotation columns (spec §4.4 S3). The shape differential is
// the default sort; a thin single-name sector can never top either (S4).
type SortKey = "shape" | "temporal";

function pct(share: number): string {
  return `${Math.round(share * 100)}%`;
}

function signedPct(value: number): string {
  const p = Math.round(value * 100);
  return `${p > 0 ? "+" : ""}${p}pp`;
}

/**
 * The sector strength and rotation board, plus the ranked-industry board
 * (spec §4.4 / ticket 07). All 11 sectors always render, even at 0% on every
 * lookback (S8). Both rotation columns are sortable, the shape differential the
 * default; a sector with fewer than two decile members cannot top the board and
 * sorts into a separate group below (S4). The `regime` prop, once ticket 10's
 * banner is wired in, adds the pullback note under CHOPPY / HOSTILE (S7).
 */
export default function SectorTable({
  market,
  regime,
}: {
  market: string;
  regime?: Regime;
}) {
  const [data, setData] = useState<SectorsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("shape");

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    fetchSectors(market)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [market]);

  // Sort within the eligibility groups: the rotation-ineligible sectors always
  // sort below the eligible ones (the k >= 2 guard, S4), and within each group
  // by the chosen rotation column descending.
  const sorted = useMemo(() => {
    if (!data) return [];
    const value = (s: SectorStrength) =>
      sort === "shape" ? s.shape_differential : (s.temporal_delta ?? -Infinity);
    return [...data.sectors].sort((a, b) => {
      if (a.rotation_eligible !== b.rotation_eligible)
        return a.rotation_eligible ? -1 : 1;
      return value(b) - value(a);
    });
  }, [data, sort]);

  if (error)
    return (
      <p role="alert" className="sector-error">
        Could not load sectors: {error}
      </p>
    );
  if (!data) return <p>Loading sectors…</p>;

  const showPullbackNote = regime === "CHOPPY" || regime === "HOSTILE";
  const firstIneligible = sorted.findIndex((s) => !s.rotation_eligible);

  return (
    <section aria-label={`${market} sectors`} className="sector-board">
      <h2>Sector strength &amp; rotation</h2>
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
            {LOOKBACKS.map((lb) => (
              <th scope="col" key={lb}>
                {lb}
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
          {sorted.map((s, i) => (
            <tr
              key={s.sector}
              className={
                s.rotation_eligible ? "eligible" : "rotation-ineligible"
              }
              data-group-start={i === firstIneligible ? "ineligible" : undefined}
            >
              <th scope="row">{s.sector}</th>
              {LOOKBACKS.map((lb) => (
                <td key={lb} className="share">
                  {pct(s.shares[lb])}{" "}
                  <span className="kn">
                    {s.decile_counts[lb]}/{s.members}
                  </span>
                </td>
              ))}
              <td className="shape">{signedPct(s.shape_differential)}</td>
              <td
                className={
                  s.delta_low_confidence ? "temporal low-confidence" : "temporal"
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
          ))}
        </tbody>
      </table>

      <IndustryBoard data={data} />
    </section>
  );
}

function IndustryBoard({ data }: { data: SectorsResponse }) {
  if (data.industries.length === 0)
    return (
      <p className="industry-empty">
        No industry has 10 or more members to rank.
      </p>
    );
  return (
    <section aria-label="ranked industries" className="industry-board">
      <h3>Industry leadership (≥10 members)</h3>
      <table>
        <thead>
          <tr>
            <th scope="col">Industry</th>
            <th scope="col">Sector</th>
            {LOOKBACKS.map((lb) => (
              <th scope="col" key={lb}>
                {lb}
              </th>
            ))}
            <th scope="col">Δ shape</th>
          </tr>
        </thead>
        <tbody>
          {data.industries.map((ind) => (
            <tr key={ind.industry}>
              <th scope="row">{ind.industry}</th>
              <td>{ind.sector}</td>
              {LOOKBACKS.map((lb) => (
                <td key={lb} className="share">
                  {pct(ind.shares[lb])}{" "}
                  <span className="kn">
                    {ind.decile_counts[lb]}/{ind.members}
                  </span>
                </td>
              ))}
              <td className="shape">{signedPct(ind.shape_differential)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
