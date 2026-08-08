import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import {
  fetchRegime,
  fetchRuns,
  triggerRun,
  type RegimeResponse,
  type RunsResponse,
} from "./api/client";
import Board from "./Board";
import Leaders from "./Leaders";
import Setups from "./Setups";

// ── The three URL axes (spec §3.5) ───────────────────────────────────────────
//
// The URL carries destinations and only destinations: market, tab, and the
// selected sector on the drill-down. Everything else (lookback, sort, view,
// ticker query, the open sheet's symbol) stays in memory and never reaches the
// bar. The URL is the *source of truth*, not a mirror — there is no `useState`
// for market/tab/sector; one hook reads `location.search`, and setting a
// destination *is* a `pushState`.

const MARKETS = ["IDX", "US"] as const;
type Market = (typeof MARKETS)[number];
const DEFAULT_MARKET: Market = "IDX";

const TABS = [
  { id: "board", label: "Board" },
  { id: "leaders", label: "Leaders" },
  { id: "setups", label: "Setups" },
  { id: "sectors", label: "Sectors" },
] as const;
type Tab = (typeof TABS)[number]["id"];
const DEFAULT_TAB: Tab = "board";

// The 11-sector GECS axis (spec §2.6). The shell validates a `?sector=` against
// this axis; the per-market *pack* eject (a sector with no members in the new
// market) is the Sectors screen's job, since it needs the sectors payload.
const SECTORS = [
  "Basic Materials",
  "Communication Services",
  "Consumer Cyclical",
  "Consumer Defensive",
  "Energy",
  "Financial Services",
  "Healthcare",
  "Industrials",
  "Real Estate",
  "Technology",
  "Utilities",
] as const;

interface Destination {
  market: Market;
  tab: Tab;
  sector: string | null;
}

// How often the shell re-checks a run it kicked on open (spec §7.3). A run is a
// ~9-minute pull, so a slow cadence is plenty; the poll stops as soon as the run
// lands (run_due and running both clear).
const RUN_POLL_MS = 2500;

function tabLabel(tab: Tab): string {
  return TABS.find((t) => t.id === tab)!.label;
}

// Serialise a destination back to a canonical `location`. Defaults are omitted
// (spec §3.5): a cold open is bare `/`, and a param appears only as the
// destination diverges — so "no params at all" is a permanently valid state
// rather than something corrected on load.
function toLocation(dest: Destination): string {
  const p = new URLSearchParams();
  if (dest.market !== DEFAULT_MARKET) p.set("market", dest.market);
  if (dest.tab !== DEFAULT_TAB) p.set("tab", dest.tab);
  if (dest.tab === "sectors" && dest.sector) p.set("sector", dest.sector);
  const q = p.toString();
  return q ? `/?${q}` : "/";
}

// Resolve whatever is in the bar to an honourable destination. Unhonourable
// URLs fall back silently (spec §3.5): an unknown market → the default; the
// dissolved `?tab=workbench` → Board; a `?sector=` the axis does not carry (or
// present without `tab=sectors`) → the Sectors list. Never an error.
function parseLocation(search: string): Destination {
  const p = new URLSearchParams(search);

  const rawMarket = (p.get("market") ?? "").toUpperCase();
  const market = (MARKETS as readonly string[]).includes(rawMarket)
    ? (rawMarket as Market)
    : DEFAULT_MARKET;

  let rawTab = p.get("tab");
  if (rawTab === "workbench") rawTab = DEFAULT_TAB; // the dissolved screen
  const tab = TABS.some((t) => t.id === rawTab) ? (rawTab as Tab) : DEFAULT_TAB;

  let sector: string | null = null;
  if (tab === "sectors") {
    const rawSector = p.get("sector");
    if (rawSector && (SECTORS as readonly string[]).includes(rawSector)) {
      sector = rawSector;
    }
  }

  return { market, tab, sector };
}

// The label a history navigation announces (spec §8.8): the destination on the
// three URL axes and only those — never the mechanism ("went back to…" tells
// the user the one thing they already know).
function destinationLabel(dest: Destination): string {
  if (dest.tab === "sectors" && dest.sector) {
    return `${dest.sector}, Sectors, ${dest.market}`;
  }
  return `${tabLabel(dest.tab)}, ${dest.market}`;
}

// Parse the bar and, if it carries an unhonourable or non-canonical destination,
// rewrite it to its canonical form via `replace` (spec §3.5/§8.8) so back/forward
// never replay a dead one. Returns the resolved destination.
function canonicaliseLocation(): Destination {
  const dest = parseLocation(window.location.search);
  const canonical = toLocation(dest);
  if (canonical !== window.location.pathname + window.location.search) {
    window.history.replaceState(null, "", canonical);
  }
  return dest;
}

/**
 * The shell's single routing seam (spec §3.5). `location.search` is the one
 * source of truth for market/tab/sector; `navigate` pushes a new destination,
 * `popstate` reads one back. Unhonourable URLs are rewritten via `replace` so no
 * dead destination survives to be replayed by back/forward.
 */
function useDestination(): {
  dest: Destination;
  navigate: (patch: Partial<Destination>) => void;
  announcement: string;
} {
  // The URL is the single source of truth (spec §3.5): `dest` is derived from
  // `location.search` on *every* render — there is no `useState` mirroring
  // market/tab/sector, so there is no second copy to drift from the bar. A
  // navigation is a history write plus a re-render tick; that tick is the hook's
  // only piece of local state that concerns the three axes.
  const [, tick] = useReducer((n: number) => n + 1, 0);
  // The destination-change region (spec §8.7/§8.8): announces on `popstate`
  // only, never on pushes — a tab or market click already announces through the
  // control's own role, name and state.
  const [announcement, setAnnouncement] = useState("");

  // Canonicalise on load: an unhonourable cold-open URL is resolved and rewritten
  // with no announcement (spec §8.8) so back/forward never replay it. `dest` is
  // already honourable this render — parseLocation resolves it regardless of the
  // raw bar — so the rewrite needs no tick.
  useEffect(() => {
    canonicaliseLocation();
  }, []);

  useEffect(() => {
    function onPop() {
      const next = canonicaliseLocation();
      tick();
      setAnnouncement(destinationLabel(next));
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((patch: Partial<Destination>) => {
    // Read the current destination back from the bar, not from a mirror — the
    // URL is the truth even mid-navigation.
    const prev = parseLocation(window.location.search);
    const next: Destination = { ...prev, ...patch };
    // The reset rule (spec §3.4): a market switch resets the drill-down. The
    // rest of the entity-naming reset (symbol, ticker query) lives in the
    // screens, which key that state off `market`; view-shape state survives.
    if (patch.market && patch.market !== prev.market) next.sector = null;
    if (next.tab !== "sectors") next.sector = null;
    window.history.pushState(null, "", toLocation(next));
    // A push announces nothing (spec §8.8). Clearing also stops a prior
    // popstate's label from lingering in the region and lets an identical later
    // destination re-announce.
    setAnnouncement("");
    tick();
  }, []);

  const dest = parseLocation(window.location.search);
  return { dest, navigate, announcement };
}

/**
 * The v2 app shell (spec §3): the chrome every screen sits inside. Full-bleed
 * frame with the content column capped at `--container-shell`; the header
 * carries product name, as-of session, the tab row and the market control; the
 * permanent regime band and the abnormal-only run-status banner sit beneath it.
 * Run-on-open and its poll live here in shell lifecycle (spec §3.6), rehomed
 * from the dissolved Workbench.
 */
export default function App() {
  const { dest, navigate, announcement } = useDestination();
  const { market, tab, sector } = dest;

  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [regime, setRegime] = useState<RegimeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // ── Shell lifecycle (spec §3.6): run-on-open + poll, keyed on market ────────
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setRuns(null);
    setRegime(null);
    setError(null);
    setDismissed(false);

    // Run-on-open: if the market's last final session is missing from the store,
    // kick a run once and poll until it lands. The served session stays the last
    // *published* one throughout — a run in progress never shows a half-written
    // session.
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

    // The regime is its own resource endpoint (spec §7.5); the band reads it
    // independently and gates nothing.
    fetchRegime(market)
      .then((r) => live && setRegime(r))
      .catch(() => {
        // A regime read failure is an identity-read failure (spec §8.7): it
        // surfaces through the same single alert as a runs read failure.
        if (live) setError((prev) => prev ?? "regime unavailable");
      });

    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [market]);

  // `document.title` per screen (spec §8.5, SC 2.4.2). It keys off the in-memory
  // destination values whether or not the URL carries them, so 2.4.2 is
  // discharged independently of the routing decision. **Not an announcement
  // mechanism** (spec §8.5) — the destination region owns that.
  useEffect(() => {
    const screen = tab === "sectors" && sector ? sector : tabLabel(tab);
    document.title = `${screen} · ${market} · Screening Dashboard`;
  }, [tab, sector, market]);

  const asOf = runs?.latest?.session ?? null;

  // The identity/body seam, the shell half (spec §7.1/§7.2/§7.3). Identity reads
  // gate the tab body: no screen mounts until the read resolves to a real
  // session. The four branches below are exclusive and never overlap.
  function tabBody(): ReactNode {
    if (error) {
      // Identity-read failure: the app's single `role="alert"`, in the tab
      // body's place, with NO screen behind it (spec §7.1/§8.7). Reachability
      // is what fails here — a failed *run* is a status, not this alert.
      return (
        <p role="alert" className="identity-error">
          Could not reach the backend: {error}
        </p>
      );
    }
    if (runs === null) {
      // The identity read is still in flight; the shell blocks on it ALONE
      // (spec §7.3) — a plain `aria-busy` container, not a whole-screen skeleton
      // gated on every read, and NOT a `role="status"` region: the closed set of
      // three polite regions is a decision (spec §8.7), and an initial load is
      // not one of them. Each panel paints itself once a screen mounts.
      return (
        <p aria-busy="true" className="shell-loading">
          Loading {market}…
        </p>
      );
    }
    if (asOf === null) {
      // The shell owns `session: null` EXCLUSIVELY (spec §7.2): one statement,
      // once, replacing the whole tab body — a screen never mounts with it. A
      // failed run is a different register: the run-status banner already speaks
      // it, so the body stays silent rather than double-reporting.
      if (runs.run_error) return null;
      return (
        <p className="empty-state no-run-yet">
          No run yet for {market}. Nothing to show tonight.
        </p>
      );
    }
    return (
      <Screen
        tab={tab}
        market={market}
        sector={sector}
        navigate={navigate}
        universeSize={runs.universe_size}
      />
    );
  }

  return (
    <div className="shell">
      {/* Bypass block (spec §8.5, SC 2.4.1): a visually-hidden skip link that
          appears on focus — landmarks alone do nothing for a sighted keyboard
          user. */}
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <header className="shell-header" role="banner">
        <div className="shell-cap shell-header-row">
          <h1 className="shell-product">Screening Dashboard</h1>
          {asOf && (
            <p className="shell-asof">
              As of <time dateTime={asOf}>{asOf}</time>
            </p>
          )}
          <TabRow tab={tab} onSelect={(t) => navigate({ tab: t })} />
          <MarketControl market={market} onSelect={(m) => navigate({ market: m })} />
        </div>
      </header>

      {/* The destination-change live region (spec §8.7/§8.8). Visually hidden;
          announces on `popstate` only. A polite live region — kept off
          `role="status"` so it does not collide with the run-status banner.
          Named for its behaviour, not its original market-switch trigger. */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      {/* Chrome sits above the tab body ONLY when the identity read succeeded: an
          identity-read failure collapses the whole app to its single alert
          (spec §7.1), so the band and the run-status banner do not render. */}
      {!error && (
        <div className="shell-cap">
          {/* 1. The permanent regime band (spec §3.3): v1's full §4.9 banner,
              on every screen, gating nothing. Absent only before the first run
              publishes a session. */}
          {regime?.session && <RegimeBanner market={market} regime={regime} />}
          {/* 2. The run-status banner — only when abnormal (spec §3.3). */}
          <RunStatus
            market={market}
            runs={runs}
            dismissed={dismissed}
            onDismiss={() => setDismissed(true)}
          />
        </div>
      )}

      <main id="main-content" className="shell-cap shell-main">
        {tabBody()}
      </main>
    </div>
  );
}

/**
 * The tab row (spec §8.5): a `role="tablist"` with roving tabindex — arrows move
 * and activate, Tab escapes, each panel associated by `aria-controls` /
 * `aria-labelledby`. A tab change is a `pushState` destination (spec §3.5).
 */
function TabRow({ tab, onSelect }: { tab: Tab; onSelect: (t: Tab) => void }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: ReactKeyboardEvent, index: number) {
    let next = index;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (index + 1) % TABS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp")
      next = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    else return;
    e.preventDefault();
    onSelect(TABS[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div role="tablist" aria-label="Screens" className="tab-row">
      {TABS.map((t, i) => {
        const selected = t.id === tab;
        return (
          <button
            key={t.id}
            ref={(el) => (refs.current[i] = el)}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={selected}
            aria-controls="active-tabpanel"
            tabIndex={selected ? 0 : -1}
            className="tab"
            onClick={() => onSelect(t.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The market control (spec §8.5): a `radiogroup`, **not** tabs — a market switch
 * resets entity state and refetches, it does not reveal a sibling panel, so
 * calling it a tablist would promise a `tabpanel` that does not exist.
 */
function MarketControl({
  market,
  onSelect,
}: {
  market: Market;
  onSelect: (m: Market) => void;
}) {
  return (
    <div role="radiogroup" aria-label="Market" className="market-control">
      {MARKETS.map((m) => {
        const checked = m === market;
        return (
          <button
            key={m}
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className="market-item"
            onClick={() => onSelect(m)}
          >
            {m}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The run-status banner (spec §3.3) — shell chrome shown **only when abnormal**:
 * a run in progress, a run that failed, or a quarantined latest serving the last
 * good session. Polite (`role="status"`, spec §8.7 / §11.7) — the app's single
 * `role="alert"` is reserved for an identity-read failure. Dismissible.
 */
function RunStatus({
  market,
  runs,
  dismissed,
  onDismiss,
}: {
  market: Market;
  runs: RunsResponse | null;
  dismissed: boolean;
  onDismiss: () => void;
}) {
  // The identity read is in flight, or nothing has ever published: neither is an
  // abnormal *run* status, so this banner stays absent. The shell body owns both
  // — the busy line and the no-run-yet statement (spec §7.2/§7.3) — so they are
  // not answered twice in disagreeing prose (the v1 mistake, §7.2).
  if (!runs) return null;

  let body: ReactNode = null;
  let kind = "";
  if (runs.running) {
    kind = "run-progress";
    body = <>Running tonight&apos;s {market} pull — fetching the latest session…</>;
  } else if (runs.run_error) {
    kind = "run-failed";
    body = (
      <>
        Tonight&apos;s {market} run failed: {runs.run_error}
      </>
    );
  } else {
    // A quarantined latest attempt: the served `latest` is older than the last
    // attempt, so the shell carries a stale banner (spec §3.4 rules 7–8). Runs
    // arrive newest-first, so runs[0] is the last attempt.
    const newest = runs.runs[0];
    // Only when a last good session is actually being served: with no `latest`
    // there is nothing to fall back to, so the no-run-yet body owns that night.
    if (newest?.status === "quarantined" && runs.latest) {
      kind = "quarantine-banner";
      body = (
        <>
          Tonight&apos;s {market} run was quarantined — showing the last good session{" "}
          <time dateTime={runs.latest.session}>{runs.latest.session}</time>.
        </>
      );
    }
  }

  if (!body || dismissed) return null;

  return (
    <p role="status" className={kind}>
      {body}{" "}
      <button type="button" className="run-status-dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </p>
  );
}

/**
 * The persistent regime band (spec §4.9 / §3.3). Advisory only: it carries
 * state, the sizing posture in *words*, breadth and the as-of session date, and
 * gates nothing. Below 25 index bars the state is undefined (warming up), which
 * carries no posture. One band per market, never a combined global verdict; the
 * reference's coloured pill is rejected (spec §3.3).
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

/**
 * The active screen (spec §5). The four screens (Board, Leaders, Setups,
 * Sectors) and the sector drill-down land in later tickets, each wrapping its
 * body reads in `Panel`/`useBodyRead` (the state matrix, spec §7); the shell
 * renders each tab's panel with the per-panel heading and the `tabpanel`
 * association the semantics (spec §8.5) require. Screens receive `market` and
 * reset their entity-naming state (selected symbol, ticker query) off it, while
 * view-shape state survives (spec §3.4).
 */
function Screen({
  tab,
  market,
  sector,
  navigate,
  universeSize,
}: {
  tab: Tab;
  market: Market;
  sector: string | null;
  navigate: (patch: Partial<Destination>) => void;
  universeSize: number | null;
}) {
  // The Board (spec §5.1): the composite landing screen, wired here as the first
  // of the four to leave placeholder status. It sits inside the tabpanel the
  // semantics require (spec §8.5), named by the Board tab; its own `<h2>`s name
  // its panels. The other three screens and the drill-down remain placeholders
  // until #87–89.
  if (tab === "board") {
    return (
      <section id="active-tabpanel" role="tabpanel" aria-labelledby="tab-board" tabIndex={0}>
        <Board
          market={market}
          universeSize={universeSize}
          navigate={(patch) => navigate(patch as Partial<Destination>)}
        />
      </section>
    );
  }

  // Sector detail is a drill-down, not a tab: it keeps the Sectors tab lit and
  // the breadcrumb is the honest control (spec §5 / §8.5).
  if (tab === "sectors" && sector) {
    return (
      <section id="active-tabpanel" role="tabpanel" aria-labelledby="tab-sectors" tabIndex={0}>
        <nav aria-label="Breadcrumb" className="breadcrumb">
          <button type="button" className="breadcrumb-back" onClick={() => navigate({ sector: null })}>
            Sectors
          </button>
        </nav>
        <h2>{sector}</h2>
        <p className="screen-placeholder">
          The {sector} pack for {market} lands in a later ticket.
        </p>
      </section>
    );
  }

  // The Setups screen (spec §5.2): the card grid, wired to the candidate read via
  // Panel/useBodyRead and to the chart sheet via each card's ticker button and
  // mini chart. The tabpanel is named by its tab; the per-panel <h2> is visually
  // hidden because the screen's header row is the count line, not a title.
  if (tab === "setups") {
    return (
      <section id="active-tabpanel" role="tabpanel" aria-labelledby="tab-setups" tabIndex={0}>
        <h2 className="sr-only">Setups</h2>
        <Setups market={market} />
      </section>
    );
  }

  return (
    <section id="active-tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0}>
      <h2>{tabLabel(tab)}</h2>
      {tab === "leaders" ? (
        <Leaders market={market} />
      ) : (
        <p className="screen-placeholder">
          The {tabLabel(tab)} screen for {market} lands in a later ticket.
        </p>
      )}
    </section>
  );
}
