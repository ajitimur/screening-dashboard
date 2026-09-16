// PROTOTYPE — throwaway. Variant B, "Annotated ledger".
//
// Primary affordance: ONE ranked table, read top to bottom. The state is the
// first column after the name, the five shares collapse into a sparkline with
// the baseline tick, headers are plain words with the formula in a tooltip, and
// the industry board is folded into a per-row "carried by" cell. Hovering or
// focusing a row lights its industries in the compact board underneath.

import { useState } from "react";
import type { SectorsResponse } from "../api/client";
import { ShareBars } from "./Bars";
import {
  STATE_HINT,
  STATE_ORDER,
  leadingIndustriesBySector,
  multiple,
  pct,
  rotationState,
  sectorColor,
  signedPp,
  summarise,
} from "./state";

export default function VariantLedger({
  data,
  regime,
  onDrill,
  registerRow,
}: {
  data: SectorsResponse;
  regime: string | null;
  onDrill: (originKey: string, target: string) => void;
  registerRow: (key: string, el: HTMLButtonElement | null) => void;
}) {
  const [hot, setHot] = useState<string | null>(null);
  const industries = leadingIndustriesBySector(data.industries);

  const rows = [...data.sectors].sort((a, b) => {
    const sa = STATE_ORDER.indexOf(rotationState(a));
    const sb = STATE_ORDER.indexOf(rotationState(b));
    if (sa !== sb) return sa - sb;
    return b.shape_differential - a.shape_differential;
  });

  return (
    <div className="proto-ledger">
      <p className="proto-summary">
        {summarise(data)}
        {regime && <span className="proto-regime"> Regime: {regime}.</span>}
      </p>

      <table className="proto-ledger-table">
        <thead>
          <tr>
            <th scope="col">Sector</th>
            <th scope="col">
              <abbr title="Emerging: leaders now, none six months ago. Leading: both. Fading: six months ago, not now. Quiet: near baseline.">
                State
              </abbr>
            </th>
            <th scope="col">
              <abbr title="Share of members in the universe top decile, at 1W 1M 3M 6M 12M. Tick = 10% baseline. Lighter = fewer than four names.">
                Leaders by lookback
              </abbr>
            </th>
            <th scope="col">
              <abbr title="1W share as a multiple of the 10% baseline">This week</abbr>
            </th>
            <th scope="col">
              <abbr title="1W share minus 6M share (Δ shape)">Rotation</abbr>
            </th>
            <th scope="col">
              <abbr title="1M share tonight minus 1M share twenty sessions ago (Δ20d)">
                Last 20 sessions
              </abbr>
            </th>
            <th scope="col">
              <abbr title="Industries with ≥10 members whose 1W or 1M share is above 16%">
                Carried by
              </abbr>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s, i) => {
            const st = rotationState(s);
            const key = `sector:${s.sector}`;
            const ind = industries.get(s.sector);
            const prevSt = i > 0 ? rotationState(rows[i - 1]) : null;
            return (
              <tr
                key={s.sector}
                className={`proto-row proto-state-${st.toLowerCase()}`}
                data-group-start={prevSt !== st ? st : undefined}
                onMouseEnter={() => setHot(s.sector)}
                onMouseLeave={() => setHot(null)}
                onFocus={() => setHot(s.sector)}
                onBlur={() => setHot(null)}
              >
                <th scope="row">
                  <span
                    className="proto-swatch"
                    style={{ background: sectorColor(s.sector) }}
                  />
                  <button
                    type="button"
                    className="sector-link"
                    ref={(el) => registerRow(key, el)}
                    onClick={() => onDrill(key, s.sector)}
                  >
                    {s.sector}
                  </button>
                </th>
                <td>
                  <span className={`proto-state-badge proto-state-${st.toLowerCase()}`} title={STATE_HINT[st]}>
                    {st}
                  </span>
                </td>
                <td className="proto-bars-cell">
                  <ShareBars
                    shares={s.shares}
                    counts={s.decile_counts}
                    color={sectorColor(s.sector)}
                  />
                </td>
                <td className="share">
                  {multiple(s.shares["1w"])}
                  <span className="kn"> {s.decile_counts["1w"]}/{s.members}</span>
                </td>
                <td className={`shape ${s.shape_differential > 0.04 ? "up" : s.shape_differential < -0.04 ? "down" : ""}`}>
                  {signedPp(s.shape_differential)}
                </td>
                <td className={`shape ${s.delta_low_confidence ? "low-confidence" : ""}`}>
                  {s.temporal_delta === null ? "—" : signedPp(s.temporal_delta)}
                </td>
                <td className="proto-carried">
                  {ind && ind.total > 0 ? (
                    <>
                      <b>{ind.leading.length}</b>/{ind.total}
                      {ind.leading.length > 0 && (
                        <span className="proto-carried-names">
                          {" "}
                          {ind.leading.slice(0, 2).map((x) => x.industry).join(", ")}
                          {ind.leading.length > 2 && ` +${ind.leading.length - 2}`}
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="kn">no industry ≥10</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <section className="proto-board" aria-label="Industry leadership">
        <h3 className="proto-lane-title">Industries leading this week</h3>
        <ul className="proto-chips">
          {[...data.industries]
            .filter((x) => x.shares["1w"] >= 0.16 || x.shares["1m"] >= 0.16)
            .sort((a, b) => b.shares["1w"] - a.shares["1w"])
            .map((x) => (
              <li
                key={x.industry}
                className={`proto-chip ${hot && hot !== x.sector ? "dim" : ""} ${hot === x.sector ? "hot" : ""}`}
                style={{ borderColor: sectorColor(x.sector) }}
              >
                <button type="button" className="sector-link" onClick={() => onDrill(`industry:${x.industry}`, x.sector)}>
                  {x.industry}
                </button>
                <span className="kn"> {pct(x.shares["1w"])} · {x.sector}</span>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}
