import { describe, expect, it, vi } from "vitest";
import * as fx from "./fixtures";

// The nine-endpoint contract, each built off `schema.d.ts`. These assert the
// module constructs a contract-valid default and that its phase-2 nullable
// fields are constructible and default to `null` (spec §9.2).
describe("the typed fixture module", () => {
  it("builds every endpoint's response with a contract-valid default", () => {
    expect(fx.runsResponse().latest?.status).toBe("published");
    expect(fx.runTriggerResponse().triggered).toBe(true);
    expect(fx.leadersResponse().boards[0].rows[0].symbol).toBe("WIN");
    expect(fx.regimeResponse().state).toBe("FRIENDLY");
    expect(fx.candidatesResponse().candidates[0].symbol).toBe("AAA");
    expect(fx.chartResponse().candles).toHaveLength(1);
    // The full 11-sector GECS axis, always.
    expect(fx.sectorsResponse().sectors).toHaveLength(11);
    expect(fx.sectorsResponse().taxonomy).toBe("GECS");
    expect(fx.sectorDetailResponse().members[0].symbol).toBe("AAA");
  });

  it("defaults every phase-2 nullable field to null", () => {
    expect(fx.candidate().verdict).toBeNull();
    expect(fx.leader().cutoffs).toBeNull();
    expect(fx.sectorMember().pct_of_52w_high).toBeNull();
    expect(fx.sectorMember().verdict).toBeNull();
  });

  it("makes phase-2 fields constructible when a test wants them populated", () => {
    expect(fx.candidate({ verdict: "ready" }).verdict).toBe("ready");
  });

  it("applies a shallow override without disturbing the other fields", () => {
    const r = fx.runsResponse({ market: "US", universe_size: 288 });
    expect(r.market).toBe("US");
    expect(r.universe_size).toBe(288);
    expect(r.latest?.market).toBe("IDX"); // untouched leaf default
  });
});

describe("the shared fetch harness", () => {
  it("routes each endpoint to its typed default, sector-detail before sectors", () => {
    expect(fx.resolveRoute({}, "/api/runs/IDX")).toMatchObject({ market: "IDX" });
    expect(fx.resolveRoute({}, "/api/runs/IDX", "POST")).toMatchObject({ triggered: true });
    expect(fx.resolveRoute({}, "/api/leaders/US")).toMatchObject({ market: "US", boards: expect.any(Array) });
    expect(fx.resolveRoute({}, "/api/regime/IDX")).toMatchObject({ state: "FRIENDLY" });
    expect(fx.resolveRoute({}, "/api/candidates/IDX")).toMatchObject({ ordered_by: "score" });
    expect(fx.resolveRoute({}, "/api/chart/IDX/AAA")).toMatchObject({ symbol: "AAA" });
    // The sectors path is a prefix of the sector-detail path; detail wins.
    expect(fx.resolveRoute({}, "/api/sectors/IDX")).toMatchObject({ sectors: expect.any(Array) });
    const detail = fx.resolveRoute({}, "/api/sectors/IDX/Consumer%20Cyclical");
    expect(detail).toMatchObject({ sector: "Consumer Cyclical", members: expect.any(Array) });
  });

  it("lets a test override just the endpoints it exercises", () => {
    const routes: fx.ApiRoutes = {
      candidates: (market) => fx.candidatesResponse({ market, candidates: [] }),
    };
    expect(fx.resolveRoute(routes, "/api/candidates/US")).toMatchObject({ candidates: [] });
    // An un-overridden endpoint still serves its default.
    expect(fx.resolveRoute(routes, "/api/regime/US")).toMatchObject({ state: "FRIENDLY" });
  });

  it("installs a fetch stub that serves the routes", async () => {
    fx.stubFetch(vi, { regime: (m) => fx.regimeResponse({ market: m, state: "HOSTILE" }) });
    const resp = await fetch("/api/regime/IDX");
    expect(await resp.json()).toMatchObject({ state: "HOSTILE" });
    vi.unstubAllGlobals();
  });
});
