// PROTOTYPE — throwaway. Variant A, "Briefing lanes".
//
// Primary affordance: the ROTATION STATE. One summary sentence, then sectors
// dealt into lanes by state (Emerging · Leading · Fading · Quiet · Thin). Each
// card shows the share sparkline, the multiple of baseline, the 20-session
// move and which industries carry it. No table at all.

import type { SectorsResponse, SectorStrength } from "../api/client";
import { ShareBars } from "./Bars";
import {
  STATE_HINT,
  STATE_ORDER,
  leadingIndustriesBySector,
  multiple,
  rotationState,
  sectorColor,
  signedPp,
  summarise,
  type RotationState,
} from "./state";

export default function VariantBriefing({
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
  const lanes = new Map<RotationState, SectorStrength[]>();
  for (const s of data.sectors) {
    const st = rotationState(s);
    lanes.set(st, [...(lanes.get(st) ?? []), s]);
  }
  for (const xs of lanes.values())
    xs.sort((a, b) => b.shape_differential - a.shape_differential);
  const industries = leadingIndustriesBySector(data.industries);

  return (
    <div className="proto-briefing">
      <p className="proto-summary">
        {summarise(data)}
        {regime && (
          <span className="proto-regime"> Regime: {regime}.</span>
        )}
      </p>

      <div className="proto-lanes">
        {STATE_ORDER.map((st) => {
          const xs = lanes.get(st) ?? [];
          return (
            <section
              key={st}
              className={`proto-lane proto-lane-${st.toLowerCase()}`}
              aria-label={st}
            >
              <h3 className="proto-lane-title">
                {st} <span className="proto-lane-count">{xs.length}</span>
              </h3>
              <p className="proto-lane-hint">{STATE_HINT[st]}</p>
              {xs.length === 0 && <p className="proto-lane-empty">none</p>}
              {xs.map((s) => {
                const key = `sector:${s.sector}`;
                const ind = industries.get(s.sector);
                const color = sectorColor(s.sector);
                return (
                  <article key={s.sector} className="proto-card">
                    <header className="proto-card-head">
                      <span className="proto-swatch" style={{ background: color }} />
                      <button
                        type="button"
                        className="sector-link"
                        ref={(el) => registerRow(key, el)}
                        onClick={() => onDrill(key, s.sector)}
                      >
                        {s.sector}
                      </button>
                    </header>
                    <ShareBars
                      shares={s.shares}
                      counts={s.decile_counts}
                      color={color}
                      height={44}
                    />
                    <dl className="proto-facts">
                      <div>
                        <dt>this week</dt>
                        <dd>
                          {multiple(s.shares["1w"])} baseline
                          <span className="kn">
                            {" "}
                            {s.decile_counts["1w"]}/{s.members}
                          </span>
                        </dd>
                      </div>
                      <div>
                        <dt>vs six months</dt>
                        <dd>{signedPp(s.shape_differential)}</dd>
                      </div>
                      <div>
                        <dt>last 20 sessions</dt>
                        <dd className={s.delta_low_confidence ? "low-confidence" : ""}>
                          {s.temporal_delta === null
                            ? "—"
                            : signedPp(s.temporal_delta)}
                        </dd>
                      </div>
                    </dl>
                    {ind && ind.total > 0 && (
                      <p className="proto-industries">
                        {ind.leading.length} of {ind.total} industries leading
                        {ind.leading.length > 0 && (
                          <>
                            : {ind.leading.slice(0, 3).map((i) => i.industry).join(", ")}
                            {ind.leading.length > 3 && " …"}
                          </>
                        )}
                      </p>
                    )}
                  </article>
                );
              })}
            </section>
          );
        })}
      </div>
    </div>
  );
}
