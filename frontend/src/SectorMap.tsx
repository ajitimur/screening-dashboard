import { useState } from "react";
import type { SectorStrength, SectorsResponse } from "./api/client";
import {
  BASELINE,
  STATE_HINT,
  leadingIndustriesBySector,
  orderByRotation,
  rotationState,
  sectorColor,
  summarise,
} from "./rotation";

// ── The rotation map (spec §5.4, the chosen shape) ───────────────────────────
//
// One picture and one list, side by side. The picture plots every sector on a
// plane whose horizontal axis is the share of leaders six months ago and whose
// vertical axis is the share this week: above the diagonal is gaining, below is
// losing, and the four corners are the four rotation states. The 20-session
// move draws as a dashed tail so a turn inside the month is visible too.
//
// The list beside it is the accessible surface and the focus-restore target:
// every sector is a real <button> into detail, every leading industry under it
// is a real <button> into its PARENT sector (spec §5.4). The bubbles are a
// second way in for a pointer, not the only way in.
//
// Chosen over the two-band table and a lane layout by prototype; the full set
// of variants is on branch `worktree-prototype+sectors-ui`.

const W = 520;
const H = 420;
const PAD = { l: 44, r: 16, t: 20, b: 40 };
// A 50% share sits at the edge of the plane; anything above clamps to it.
const MAX = 0.5;
// The corner boundaries mirror the state cut lines in rotation.ts.
const LEAD_LINE = 0.16;
const ESTABLISHED_LINE = 0.18;

function sx(v: number) {
  return PAD.l + (Math.min(v, MAX) / MAX) * (W - PAD.l - PAD.r);
}
function sy(v: number) {
  return H - PAD.b - (Math.min(v, MAX) / MAX) * (H - PAD.t - PAD.b);
}

function pct(share: number): string {
  return `${Math.round(share * 100)}%`;
}
function signedPp(value: number): string {
  const p = Math.round(value * 100);
  return `${p > 0 ? "+" : ""}${p}pp`;
}

export default function SectorMap({
  data,
  onDrill,
  registerRow,
}: {
  data: SectorsResponse;
  onDrill: (originKey: string, target: string) => void;
  registerRow: (key: string, el: HTMLButtonElement | null) => void;
}) {
  // The sector under the pointer, on either side: the other side dims to it.
  const [hot, setHot] = useState<string | null>(null);
  const industries = leadingIndustriesBySector(data.industries);
  const ordered = orderByRotation(data.sectors);
  const maxMembers = Math.max(1, ...data.sectors.map((s) => s.members));
  const radius = (s: SectorStrength) => 8 + 16 * Math.sqrt(s.members / maxMembers);

  return (
    <div className="sector-map">
      <p className="sector-summary">{summarise(data)}</p>

      <div className="sector-map-row">
        <svg
          className="sector-plot"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Sector rotation map: share of leaders six months ago against share of leaders this week"
        >
          <rect x={sx(0)} y={sy(MAX)} width={sx(ESTABLISHED_LINE) - sx(0)} height={sy(LEAD_LINE) - sy(MAX)} className="sector-quad sector-quad-emerging" />
          <rect x={sx(ESTABLISHED_LINE)} y={sy(MAX)} width={sx(MAX) - sx(ESTABLISHED_LINE)} height={sy(LEAD_LINE) - sy(MAX)} className="sector-quad sector-quad-leading" />
          <rect x={sx(ESTABLISHED_LINE)} y={sy(LEAD_LINE)} width={sx(MAX) - sx(ESTABLISHED_LINE)} height={sy(0) - sy(LEAD_LINE)} className="sector-quad sector-quad-fading" />
          <rect x={sx(0)} y={sy(LEAD_LINE)} width={sx(ESTABLISHED_LINE) - sx(0)} height={sy(0) - sy(LEAD_LINE)} className="sector-quad sector-quad-quiet" />

          <text x={sx(0.01)} y={sy(MAX) + 12} className="sector-quad-label">EMERGING · rotating in</text>
          <text x={sx(MAX) - 4} y={sy(MAX) + 12} textAnchor="end" className="sector-quad-label">LEADING</text>
          <text x={sx(MAX) - 4} y={sy(0) - 6} textAnchor="end" className="sector-quad-label">FADING · rotating out</text>
          <text x={sx(0.01)} y={sy(0) - 6} className="sector-quad-label">QUIET</text>

          <line x1={sx(BASELINE)} x2={sx(BASELINE)} y1={sy(0)} y2={sy(MAX)} className="sector-baseline" />
          <line x1={sx(0)} x2={sx(MAX)} y1={sy(BASELINE)} y2={sy(BASELINE)} className="sector-baseline" />
          <line x1={sx(0)} x2={sx(MAX)} y1={sy(0)} y2={sy(MAX)} className="sector-diagonal" />

          {[0, 0.1, 0.2, 0.3, 0.4, 0.5].map((v) => (
            <g key={v}>
              <text x={sx(v)} y={H - PAD.b + 14} textAnchor="middle" className="sector-tick">{pct(v)}</text>
              <text x={PAD.l - 6} y={sy(v) + 3} textAnchor="end" className="sector-tick">{pct(v)}</text>
            </g>
          ))}
          <text x={(sx(0) + sx(MAX)) / 2} y={H - 6} textAnchor="middle" className="sector-axis">leaders six months ago (6M share)</text>
          <text x={12} y={(sy(0) + sy(MAX)) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(sy(0) + sy(MAX)) / 2})`} className="sector-axis">leaders this week (1W share)</text>

          {data.sectors.map((s) => {
            const x = sx(s.shares["6m"] ?? 0);
            const y = sy(s.shares["1w"] ?? 0);
            const color = sectorColor(s.sector);
            const r = radius(s);
            const dim = hot !== null && hot !== s.sector;
            const tailFrom =
              s.temporal_delta === null || s.delta_low_confidence
                ? null
                : sy(Math.max(0, (s.shares["1w"] ?? 0) - s.temporal_delta));
            return (
              <g
                key={s.sector}
                className={`sector-bubble${dim ? " dim" : ""}${s.rotation_eligible ? "" : " thin"}`}
                aria-hidden="true"
                onClick={() => onDrill(`sector:${s.sector}`, s.sector)}
                onMouseEnter={() => setHot(s.sector)}
                onMouseLeave={() => setHot(null)}
              >
                {tailFrom !== null && (
                  <line x1={x} x2={x} y1={tailFrom} y2={y} stroke={color} strokeWidth={2} strokeDasharray="3 2" opacity={0.6} />
                )}
                <circle cx={x} cy={y} r={r} fill={color} fillOpacity={s.rotation_eligible ? 0.75 : 0.25} stroke={color} strokeWidth={1.5} />
                <text x={x + r + 4} y={y + 4} className="sector-bubble-label">{s.sector}</text>
              </g>
            );
          })}
        </svg>

        <ol className="sector-map-list" aria-label="Sectors by rotation state">
          {ordered.map((s) => {
            const st = rotationState(s);
            const key = `sector:${s.sector}`;
            const leading = industries.get(s.sector) ?? [];
            return (
              <li
                key={s.sector}
                className={`sector-map-item${hot === s.sector ? " hot" : ""}`}
                onMouseEnter={() => setHot(s.sector)}
                onMouseLeave={() => setHot(null)}
              >
                <span className="sector-swatch" style={{ background: sectorColor(s.sector) }} aria-hidden="true" />
                <button
                  type="button"
                  className="sector-link"
                  ref={(el) => registerRow(key, el)}
                  onClick={() => onDrill(key, s.sector)}
                >
                  {s.sector}
                </button>
                <span className={`sector-state sector-state-${st.toLowerCase()}`} title={STATE_HINT[st]}>
                  {st}
                </span>
                <span className="kn">
                  {" "}
                  {pct(s.shares["1w"] ?? 0)} this week ({s.decile_counts["1w"] ?? 0}/{s.members}) ·{" "}
                  {signedPp(s.shape_differential)} vs 6M
                  {s.temporal_delta !== null && !s.delta_low_confidence && (
                    <> · {signedPp(s.temporal_delta)} in 20 sessions</>
                  )}
                </span>
                {leading.length > 0 && (
                  <ul className="sector-map-industries" aria-label={`${s.sector} industries leading`}>
                    {leading.map((i) => (
                      <li key={i.industry}>
                        <button
                          type="button"
                          className="sector-link"
                          ref={(el) => registerRow(`industry:${i.industry}`, el)}
                          onClick={() => onDrill(`industry:${i.industry}`, s.sector)}
                        >
                          {i.industry}
                        </button>
                        <span className="kn"> {pct(i.shares["1w"] ?? 0)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      <p className="band-subtitle">
        Bubble size is member count. The dashed tail is the 20-session move in leader share.
        Faint bubbles have fewer than two leaders this week.
      </p>
    </div>
  );
}
