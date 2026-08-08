// One typed fixture module for the whole nine-endpoint contract (spec §9.2).
//
// v1's five test files each hand-rolled their own route map — ~1,100 lines of
// fixture plumbing whose facts drifted file to file. This module constructs
// every endpoint's response *once*, typed off the generated `schema.d.ts`, so a
// renamed or retyped backend field is a typecheck failure here rather than a
// stale literal in five places. Each builder takes a partial override and fills
// the rest with a contract-valid default; the **phase-2 nullable fields are
// constructible and default to `null`**, so a phase-1 payload is built as
// contract-valid rather than improvised.
//
// The harness itself is unchanged: `stubFetch` installs a `vi.stubGlobal`
// fetch (no MSW — spec §9.2). Tests that need in-flight control (the
// market-switch skeletons) keep supplying their own deferred promise; tests
// that need the URL contract keep using jsdom's `history`/`popstate`.
import type { components } from "./schema";

type Schemas = components["schemas"];

// A builder returns a fully-typed value; the override is a shallow patch, so a
// test names only the fields it cares about and the rest stay contract-valid.
function builder<T>(defaults: () => T): (overrides?: Partial<T>) => T {
  return (overrides = {}) => ({ ...defaults(), ...overrides });
}

// ── Leaf rows ──────────────────────────────────────────────────────────────

export const runRecord = builder<Schemas["RunRecord"]>(() => ({
  market: "IDX",
  session: "2026-08-04",
  status: "published",
  symbols_enumerated: 100,
  symbols_resolved: 100,
  created_at: "2026-08-04T22:00:00",
}));

export const scoreRow = builder<Schemas["ScoreRow"]>(() => ({
  dimension: "tightness",
  weight: 2,
  hit: true,
}));

export const candle = builder<Schemas["Candle"]>(() => ({
  session: "2026-08-04",
  open: 1,
  high: 2,
  low: 0.5,
  close: 1.5,
  volume: 100,
}));

export const maPoint = builder<Schemas["MaPoint"]>(() => ({
  session: "2026-08-04",
  value: 1.25,
}));

export const chartFacts = builder<Schemas["ChartFacts"]>(() => ({
  base_len: 30,
  trigger: 100,
  dist_adr: 1.02,
  stopw_adr: 1.53,
  adr: 0.02,
  dollar_volume: 1_000_000, // null when the name's bars cannot supply it
  decile_ranks: { "1m": 0.95 },
  sector: "Technology", // null when the label was never fetched
}));

export const setupOverlay = builder<Schemas["SetupOverlay"]>(() => ({
  base_start: "2026-06-01",
  cluster_start: "2026-07-15",
  trigger: 100,
  stop: 97,
  envelope: [],
  score: 3,
  breakdown: [],
}));

export const candidate = builder<Schemas["Candidate"]>(() => ({
  symbol: "AAA",
  score: 3.5,
  breakdown: [], // nullable at P2; a P1 detected row always carries the rubric
  dist_adr: 1.0,
  stopw_adr: 1.3,
  affordable: false,
  industry: "Semiconductors", // null when the label was never fetched
  breadth: 2,
  trigger_price: 100.0,
  stop_price: 97.0,
  close: 98.0,
  sector: "Technology", // null when the label was never fetched
  adr: 0.02,
  dollar_volume: 1_000_000, // null when the name's bars cannot supply it
  decile_ranks: {},
  new_tonight: false,
  verdict: null, // P2 — typed now, returned null
}));

export const leaderRow = builder<Schemas["LeaderRow"]>(() => ({
  symbol: "WIN",
  raw_return: 0.42,
  breadth: 3,
  is_new: true,
  surge: true,
  adr: 0.05, // null when it cannot be computed
  sector: "Technology", // null when the label was never fetched
  dollar_volume: 1_000_000, // null when the name's bars cannot supply it
  tier: null, // P2 — typed now, returned null
  rs_pctile: null, // P2 — typed now, returned null
}));

export const leader = builder<Schemas["Leader"]>(() => ({
  lookback: "1w",
  rows: [leaderRow()],
  cutoffs: null, // P2 — the per-lookback cutoff block, null until banding lands
}));

export const sectorStrength = builder<Schemas["SectorStrength"]>(() => ({
  sector: "Technology",
  members: 12,
  shares: { "1w": 0.3, "1m": 0.4, "3m": 0.5, "6m": 0.4, "12m": 0.35 },
  decile_counts: { "1w": 3, "1m": 4, "3m": 5, "6m": 4, "12m": 3 },
  shape_differential: 0.1,
  temporal_delta: 0.05, // nullable
  rotation_eligible: true,
  delta_low_confidence: false,
}));

export const industryStrength = builder<Schemas["IndustryStrength"]>(() => ({
  industry: "Semiconductors",
  sector: "Technology",
  members: 10,
  shares: { "1w": 0.3, "1m": 0.4, "3m": 0.5, "6m": 0.4, "12m": 0.35 },
  decile_counts: { "1w": 3, "1m": 4, "3m": 5, "6m": 4, "12m": 3 },
  shape_differential: 0.1,
}));

export const sectorMember = builder<Schemas["SectorMember"]>(() => ({
  symbol: "AAA",
  returns: { "1w": 0.1, "1m": 0.2 },
  pctile_universe: { "1w": 0.9, "1m": 0.95 },
  top_decile: { "1w": true, "1m": true },
  pct_of_52w_high: null, // P2 — no 52-week high is computed yet
  verdict: null, // P2 — null means *not evaluated*, distinct from `extended`
}));

// ── Endpoint responses ─────────────────────────────────────────────────────

// GET /api/runs/{market}
export const runsResponse = builder<Schemas["RunsResponse"]>(() => ({
  market: "IDX",
  latest: runRecord(),
  runs: [runRecord()],
  universe_size: 100,
  run_due: false,
  running: false,
  run_error: null,
}));

// POST /api/runs/{market}
export const runTriggerResponse = builder<Schemas["RunTriggerResponse"]>(() => ({
  market: "IDX",
  triggered: true,
  running: true,
}));

// GET /api/leaders/{market} (and /api/boards/{market}, the alias)
export const leadersResponse = builder<Schemas["LeadersResponse"]>(() => ({
  market: "IDX",
  session: "2026-08-04",
  boards: [leader()],
}));

// GET /api/regime/{market}
export const regimeResponse = builder<Schemas["RegimeResponse"]>(() => ({
  market: "IDX",
  session: "2026-08-04",
  state: "FRIENDLY",
  posture: "full size",
  breadth: 0.5,
}));

// GET /api/candidates/{market}
export const candidatesResponse = builder<Schemas["CandidatesResponse"]>(() => ({
  market: "IDX",
  session: "2026-08-04",
  ordered_by: "score",
  candidates: [candidate()],
}));

// GET /api/chart/{market}/{symbol}
export const chartResponse = builder<Schemas["ChartResponse"]>(() => ({
  market: "IDX",
  symbol: "AAA",
  session: "2026-08-04",
  candles: [candle()],
  sma10: [],
  sma20: [],
  sma50: [],
  ema65: [],
  setup: null,
  facts: chartFacts(),
}));

// The 11-sector GECS axis (spec §2.6) — the full axis a SectorsResponse always
// carries, so the empty-state default is still contract-shaped.
export const SECTORS = [
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

// GET /api/sectors/{market}
export const sectorsResponse = builder<Schemas["SectorsResponse"]>(() => ({
  market: "IDX",
  session: "2026-08-04",
  taxonomy: "GECS",
  sectors: SECTORS.map((sector) => sectorStrength({ sector })),
  industries: [industryStrength()],
}));

// GET /api/sectors/{market}/{sector}
export const sectorDetailResponse = builder<Schemas["SectorDetailResponse"]>(() => ({
  market: "IDX",
  sector: "Technology",
  session: "2026-08-04",
  taxonomy: "GECS",
  members: [sectorMember()],
}));

// ── The fetch harness ──────────────────────────────────────────────────────

// Every response the router can serve, keyed by the path it answers. A test
// overrides only the endpoints it exercises; the rest fall back to a contract-
// valid default. Order matters: the sector-detail path is a superstring of the
// sectors path, so it is matched first.
export interface ApiRoutes {
  runs?: (market: string) => Schemas["RunsResponse"];
  runTrigger?: (market: string) => Schemas["RunTriggerResponse"];
  leaders?: (market: string) => Schemas["LeadersResponse"];
  sectorDetail?: (market: string, sector: string) => Schemas["SectorDetailResponse"];
  sectors?: (market: string) => Schemas["SectorsResponse"];
  regime?: (market: string) => Schemas["RegimeResponse"];
  candidates?: (market: string) => Schemas["CandidatesResponse"];
  chart?: (market: string, symbol: string) => Schemas["ChartResponse"];
}

// Resolve a request to its typed response body. Kept as a pure function so a
// test that needs in-flight control (the market-switch skeletons, spec §9.2)
// can wrap the body in its own deferred promise instead of resolving now.
export function resolveRoute(routes: ApiRoutes, url: string, method = "GET"): unknown {
  const path = new URL(url, "http://test").pathname;
  const seg = path.split("/").filter(Boolean); // ["api", "runs", "IDX", ...]
  const market = (seg[2] ?? "").toUpperCase();

  if (path.includes("/api/runs/")) {
    return method === "POST"
      ? (routes.runTrigger ?? ((m) => runTriggerResponse({ market: m })))(market)
      : (routes.runs ?? ((m) => runsResponse({ market: m })))(market);
  }
  if (path.includes("/api/leaders/") || path.includes("/api/boards/"))
    return (routes.leaders ?? ((m) => leadersResponse({ market: m })))(market);
  if (path.includes("/api/sectors/") && seg.length >= 4) {
    const sector = decodeURIComponent(seg[3]);
    return (routes.sectorDetail ??
      ((m, s) => sectorDetailResponse({ market: m, sector: s })))(market, sector);
  }
  if (path.includes("/api/sectors/"))
    return (routes.sectors ?? ((m) => sectorsResponse({ market: m })))(market);
  if (path.includes("/api/regime/"))
    return (routes.regime ?? ((m) => regimeResponse({ market: m })))(market);
  if (path.includes("/api/candidates/"))
    return (routes.candidates ?? ((m) => candidatesResponse({ market: m })))(market);
  if (path.includes("/api/chart/")) {
    const symbol = decodeURIComponent(seg[3] ?? "");
    return (routes.chart ??
      ((m, s) => chartResponse({ market: m, symbol: s })))(market, symbol);
  }
  throw new Error(`fixtures: no route for ${method} ${path}`);
}

// Install a `vi.stubGlobal("fetch", …)` that serves the routes. Requires the
// `vi` from the caller's suite (the type is import-only, so this module is
// import-safe outside vitest).
export function stubFetch(vi: typeof import("vitest").vi, routes: ApiRoutes = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, opts?: { method?: string }) => {
      const body = resolveRoute(routes, url, opts?.method ?? "GET");
      return { ok: true, json: async () => body } as Response;
    }),
  );
}
