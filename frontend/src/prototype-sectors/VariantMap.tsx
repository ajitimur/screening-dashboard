// PROTOTYPE — throwaway. Variant C, "Rotation map".
//
// Primary affordance: a PICTURE. Each sector is a bubble on a plane whose
// horizontal axis is "share of leaders six months ago" and vertical axis is
// "share of leaders this week". Above the diagonal = gaining, below = losing.
// The four corners are the four states. The 20-session move draws as a tail.
// A ranked list beside the plot carries the real buttons and the industries.

import { useState } from "react";
import type { SectorsResponse, SectorStrength } from "../api/client";
import {
  BASELINE,
  STATE_ORDER,
  leadingIndustriesBySector,
  pct,
  rotationState,
  sectorColor,
  signedPp,
  summarise,
} from "./state";

const W = 520;
const H = 420;
const PAD = { l: 44, r: 16, t: 20, b: 40 };
const MAX = 0.5;

function sx(v: number) {
  return PAD.l + (Math.min(v, MAX) / MAX) * (W - PAD.l - PAD.r);
}
function sy(v: number) {
  return H - PAD.b - (Math.min(v, MAX) / MAX) * (H - PAD.t - PAD.b);
}

export default function VariantMap({
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
  const maxMembers = Math.max(...data.sectors.map((s) => s.members));
  const r = (s: SectorStrength) => 8 + 16 * Math.sqrt(s.members / maxMembers);

  const ordered = [...data.sectors].sort((a, b) => {
    const sa = STATE_ORDER.indexOf(rotationState(a));
    const sb = STATE_ORDER.indexOf(rotationState(b));
    if (sa !== sb) return sa - sb;
    return b.shape_differential - a.shape_differential;
  });

  return (
    <div className="proto-map">
      <p className="proto-summary">
        {summarise(data)}
        {regime && <span className="proto-regime"> Regime: {regime}.</span>}
      </p>

      <div className="proto-map-row">
        <svg
          className="proto-plot"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Sector rotation map: six-month leader share against this-week leader share"
        >
          {/* quadrant shading */}
          <rect x={sx(0)} y={sy(MAX)} width={sx(0.18) - sx(0)} height={sy(0.16) - sy(MAX)} className="proto-q proto-q-emerging" />
          <rect x={sx(0.18)} y={sy(MAX)} width={sx(MAX) - sx(0.18)} height={sy(0.16) - sy(MAX)} className="proto-q proto-q-leading" />
          <rect x={sx(0.18)} y={sy(0.16)} width={sx(MAX) - sx(0.18)} height={sy(0) - sy(0.16)} className="proto-q proto-q-fading" />
          <rect x={sx(0)} y={sy(0.16)} width={sx(0.18) - sx(0)} height={sy(0) - sy(0.16)} className="proto-q proto-q-quiet" />

          <text x={sx(0.01)} y={sy(MAX) + 12} className="proto-qlabel">EMERGING · rotating in</text>
          <text x={sx(MAX) - 4} y={sy(MAX) + 12} textAnchor="end" className="proto-qlabel">LEADING</text>
          <text x={sx(MAX) - 4} y={sy(0) - 6} textAnchor="end" className="proto-qlabel">FADING · rotating out</text>
          <text x={sx(0.01)} y={sy(0) - 6} className="proto-qlabel">QUIET</text>

          {/* baseline ticks and the no-change diagonal */}
          <line x1={sx(BASELINE)} x2={sx(BASELINE)} y1={sy(0)} y2={sy(MAX)} className="proto-baseline-line" />
          <line x1={sx(0)} x2={sx(MAX)} y1={sy(BASELINE)} y2={sy(BASELINE)} className="proto-baseline-line" />
          <line x1={sx(0)} x2={sx(MAX)} y1={sy(0)} y2={sy(MAX)} className="proto-diagonal" />

          {/* axes */}
          {[0, 0.1, 0.2, 0.3, 0.4, 0.5].map((v) => (
            <g key={v}>
              <text x={sx(v)} y={H - PAD.b + 14} textAnchor="middle" className="proto-tick">{pct(v)}</text>
              <text x={PAD.l - 6} y={sy(v) + 3} textAnchor="end" className="proto-tick">{pct(v)}</text>
            </g>
          ))}
          <text x={(sx(0) + sx(MAX)) / 2} y={H - 6} textAnchor="middle" className="proto-axis">leaders six months ago (6M share)</text>
          <text x={12} y={(sy(0) + sy(MAX)) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(sy(0) + sy(MAX)) / 2})`} className="proto-axis">leaders this week (1W share)</text>

          {/* bubbles, with the 20-session tail */}
          {data.sectors.map((s) => {
            const x = sx(s.shares["6m"]);
            const y = sy(s.shares["1w"]);
            const color = sectorColor(s.sector);
            const dim = hot !== null && hot !== s.sector;
            const tailFrom = s.temporal_delta === null ? null : sy(Math.max(0, s.shares["1w"] - s.temporal_delta));
            return (
              <g
                key={s.sector}
                className={`proto-bubble ${dim ? "dim" : ""} ${s.rotation_eligible ? "" : "thin"}`}
                tabIndex={0}
                role="button"
                aria-label={`${s.sector}, ${rotationState(s)}`}
                onClick={() => onDrill(`sector:${s.sector}`, s.sector)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onDrill(`sector:${s.sector}`, s.sector); }}
                onMouseEnter={() => setHot(s.sector)}
                onMouseLeave={() => setHot(null)}
              >
                <title>
                  {`${s.sector}: ${rotationState(s)}. This week ${pct(s.shares["1w"])} (${s.decile_counts["1w"]}/${s.members}), six months ${pct(s.shares["6m"])}, 20-session move ${s.temporal_delta === null ? "n/a" : signedPp(s.temporal_delta)}`}
                </title>
                {tailFrom !== null && !s.delta_low_confidence && (
                  <line x1={x} x2={x} y1={tailFrom} y2={y} stroke={color} strokeWidth={2} strokeDasharray="3 2" opacity={0.6} />
                )}
                <circle cx={x} cy={y} r={r(s)} fill={color} fillOpacity={s.rotation_eligible ? 0.75 : 0.25} stroke={color} strokeWidth={1.5} />
                <text x={x + r(s) + 4} y={y + 4} className="proto-bubble-label">{s.sector}</text>
              </g>
            );
          })}
        </svg>

        <ol className="proto-map-list" aria-label="Sectors by state">
          {ordered.map((s) => {
            const st = rotationState(s);
            const key = `sector:${s.sector}`;
            const ind = industries.get(s.sector);
            return (
              <li
                key={s.sector}
                className={`proto-map-item ${hot === s.sector ? "hot" : ""}`}
                onMouseEnter={() => setHot(s.sector)}
                onMouseLeave={() => setHot(null)}
              >
                <span className="proto-swatch" style={{ background: sectorColor(s.sector) }} />
                <button
                  type="button"
                  className="sector-link"
                  ref={(el) => registerRow(key, el)}
                  onClick={() => onDrill(key, s.sector)}
                >
                  {s.sector}
                </button>
                <span className={`proto-state-badge proto-state-${st.toLowerCase()}`}>{st}</span>
                <span className="kn">
                  {" "}
                  {pct(s.shares["1w"])} this week · {signedPp(s.shape_differential)} vs 6M
                </span>
                {ind && ind.leading.length > 0 && (
                  <div className="proto-map-industries">
                    {ind.leading.slice(0, 3).map((x) => x.industry).join(" · ")}
                    {ind.leading.length > 3 && " …"}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </div>
      <p className="band-subtitle">
        Bubble size = members. Dashed tail = the 20-session move in leader share (Δ20d), drawn on the vertical axis.
        Faint bubbles have fewer than two leaders this week.
      </p>
    </div>
  );
}
