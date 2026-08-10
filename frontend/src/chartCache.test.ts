import { afterEach, describe, expect, it, vi } from "vitest";
import { loadChart, _clearChartCache } from "./chartCache";
import { chartResponse } from "./api/fixtures";

afterEach(() => {
  _clearChartCache();
  vi.restoreAllMocks();
});

function stub() {
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => chartResponse({ symbol: url.includes("BBB") ? "BBB" : "AAA" }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("the shared chart cache", () => {
  it("dedupes identical (market, symbol, bars) reads to a single fetch", async () => {
    const fetchMock = stub();
    const a = loadChart("US", "AAA", 60);
    const b = loadChart("US", "AAA", 60);
    expect(a).toBe(b); // the same in-flight promise, not two
    await Promise.all([a, b]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keys on the bar count — 60 and full are separate entries", async () => {
    const fetchMock = stub();
    await Promise.all([loadChart("US", "AAA", 60), loadChart("US", "AAA")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // The mini's 60-bar window is a query param; the full window is not.
    expect(fetchMock.mock.calls[0][0]).toContain("bars=60");
  });

  it("shares one payload between a mini chart and the sheet at the same bar count", async () => {
    const fetchMock = stub();
    // A mini paints first (bars=60); opening the sheet at the same window reuses it.
    const mini = await loadChart("US", "AAA", 60);
    const sheet = await loadChart("US", "AAA", 60);
    expect(sheet).toBe(mini);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("evicts a rejected read so a later open can retry rather than replay the failure", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        if (calls === 1) throw new Error("network");
        return { ok: true, json: async () => chartResponse() } as Response;
      }),
    );
    await expect(loadChart("US", "AAA", 60)).rejects.toThrow();
    // Not stuck on the cached rejection — the retry fetches again and resolves.
    await expect(loadChart("US", "AAA", 60)).resolves.toBeDefined();
    expect(calls).toBe(2);
  });
});
