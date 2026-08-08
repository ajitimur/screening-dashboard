import { useEffect, useRef, useState, type ReactNode } from "react";

// ── The body-owned state matrix (spec §7) ────────────────────────────────────
//
// The seam is cut by *what a read means*, not by which component issued it
// (spec §7.1). The identity reads — `/api/runs` and `/api/regime` — are the
// SHELL's: they answer *what night is this*, they gate every screen, and their
// failure is the app's single `role="alert"`. That half lives in `App.tsx`.
//
// This module is the OTHER half: the body reads. A body read is panel-owned and
// degrades in place — a dead panel keeps its frame and posts a POLITE notice,
// never an alert, so three dead panels do not shout three times (spec §7.1). It
// is the primitive every screen wraps a body read in, so the whole matrix —
// progressive paint, the market-switch skeleton, the polite failure notice — is
// written once here rather than re-improvised per screen (the v1 mistake, §7.1).

export type BodyRead<T> =
  // First-ever paint: the panel has not drawn yet and paints when ready (§7.3).
  | { status: "loading" }
  // Mid-flight market switch (§7.6): the frame stays, the values are blanked.
  | { status: "switching" }
  // A panel-owned read failed: rendered as a polite notice, never an alert.
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/**
 * Drive one body read, keyed on `market`. On the first mount the state is
 * `loading`; on a market switch it becomes `switching` **immediately** — the
 * previous market's data is dropped before the new fetch resolves, so a panel can
 * never show IDX numbers under a `US` label (spec §7.6, the one state here that
 * could produce a wrong trade). A failure resolves to `error`, which `Panel`
 * renders as a polite notice in place.
 *
 * Each panel drives its own read, so panels paint independently rather than
 * waiting on the slowest (spec §7.3) — there is no shared gate here by design.
 *
 * `fetcher` is an effect dependency, so it must be stable across renders (wrap it
 * in `useCallback`); an unstable fetcher would re-fire the read every render.
 */
export function useBodyRead<T>(
  market: string,
  fetcher: (market: string) => Promise<T>,
): BodyRead<T> {
  const [state, setState] = useState<BodyRead<T>>({ status: "loading" });
  // Distinguishes a first paint (progressive, §7.3) from a market switch (§7.6):
  // both are busy, but the switch must keep the frame while blanking the values.
  const seen = useRef(false);

  useEffect(() => {
    let live = true;
    setState(seen.current ? { status: "switching" } : { status: "loading" });
    seen.current = true;
    fetcher(market)
      .then((data) => live && setState({ status: "ready", data }))
      .catch((e) => live && setState({ status: "error", message: String(e) }));
    return () => {
      live = false;
    };
  }, [market, fetcher]);

  return state;
}

/**
 * The frame a body read is drawn inside (spec §7.1/§7.3/§7.6). It owns every
 * non-ready rendering so a screen writes only its ready content and the shape of
 * its own skeleton:
 *
 *  - **loading / switching** → the caller's `skeleton`, drawn at the panel's real
 *    dimensions with `aria-busy`. It is **static** — the shimmer, if any, is a CSS
 *    concern zeroed by `prefers-reduced-motion`; never a spinner, never a text
 *    node that collapses the layout (spec §7.6). A first paint and a market switch
 *    share the skeleton; the difference that matters — never showing stale values
 *    — is enforced in `useBodyRead`, not here.
 *  - **error** → a POLITE `role="status"` notice in the panel's frame, never a
 *    `role="alert"` (spec §7.1): the single alert is the shell's, for identity.
 *  - **ready** → the children.
 *
 * The `label` frame is rendered in every state, so the panel never blanks a
 * screen — it collapses only itself (spec §7.1).
 */
export function Panel<T>({
  label,
  read,
  skeleton,
  children,
}: {
  label: string;
  read: BodyRead<T>;
  skeleton: ReactNode;
  children: (data: T) => ReactNode;
}) {
  const busy = read.status === "loading" || read.status === "switching";
  return (
    <section className="panel" aria-label={label} aria-busy={busy || undefined}>
      {read.status === "error" ? (
        <p role="status" className="panel-notice">
          {label} is unavailable right now.
        </p>
      ) : busy ? (
        skeleton
      ) : (
        children(read.data)
      )}
    </section>
  );
}

/**
 * A **night-inflicted** empty (spec §7.4). No click on screen can make it
 * non-empty, so it carries no action: it is a FACT, stated in the panel's own
 * body copy, naming the number, that **never apologises** — five detected names
 * is a *finished* screen, not a degraded one. The wording was transcribed from
 * v1 per panel, not reinvented, so the copy is the caller's; this component is
 * only the register. Deliberately **not** a
 * `role="status"`/`role="alert"` — it is content, not an event.
 */
export function NightEmpty({ children }: { children: ReactNode }) {
  return <p className="empty-night">{children}</p>;
}

/**
 * A **filter-inflicted** empty (spec §7.4). It is recoverable — a click on
 * screen, clearing the offending filter, makes it non-empty — so by the one rule
 * ("if a click can make it non-empty, the empty state must contain that click")
 * it carries the offending chip and a clear action inline. The sharpest case is
 * the default-ON sub-4% ADR toggle emptying a Leaders table the user never
 * touched: still filter-inflicted, and it must say so rather than read as broken.
 * Neither empty register uses the error treatment.
 */
export function FilterEmpty({
  chip,
  onClear,
  children,
}: {
  chip: string;
  onClear: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="empty-filter">
      <p>{children ?? "No rows match the current filter."}</p>
      <p className="empty-filter-controls">
        <span className="chip">{chip}</span>
        <button type="button" className="chip-clear" onClick={onClear}>
          Clear filter
        </button>
      </p>
    </div>
  );
}
