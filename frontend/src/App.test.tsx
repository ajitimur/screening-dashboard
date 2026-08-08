import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";
import {
  regimeResponse,
  runRecord,
  runTriggerResponse,
  runsResponse,
  stubFetch,
  type ApiRoutes,
} from "./api/fixtures";

// The chart canvas jsdom cannot render; stub the library so the shell mounts
// (no screen renders it yet, but the mock keeps a future import harmless).
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
    priceScale: () => ({ applyOptions: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  CandlestickSeries: "Candlestick",
  LineSeries: "Line",
  HistogramSeries: "Histogram",
}));

beforeEach(() => {
  // The URL is the source of truth (spec §3.5); reset it to a bare cold open so
  // one test's destination does not leak into the next.
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ── Chrome (spec §3.3, §8.5) ─────────────────────────────────────────────────

describe("the shell — chrome", () => {
  it("carries product name, as-of session, the tab row and the market control", async () => {
    stubFetch(vi);
    render(<App />);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Screening Dashboard",
    );
    // As-of session, from the last published run (also echoed by the regime band).
    expect((await screen.findAllByText("2026-08-04")).length).toBeGreaterThan(0);
    // The tab row is a tablist (spec §8.5)...
    const tablist = screen.getByRole("tablist", { name: /screens/i });
    expect(within(tablist).getByRole("tab", { name: "Board" })).toBeInTheDocument();
    expect(within(tablist).getByRole("tab", { name: "Sectors" })).toBeInTheDocument();
    // ...and the market control is a radiogroup, NOT a tablist (spec §8.5).
    const markets = screen.getByRole("radiogroup", { name: /market/i });
    expect(within(markets).getByRole("radio", { name: "IDX" })).toBeChecked();
    expect(within(markets).getByRole("radio", { name: "US" })).not.toBeChecked();
  });

  it("exposes a skip link and the banner/main landmarks", async () => {
    stubFetch(vi);
    render(<App />);
    await screen.findAllByText("2026-08-04");

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    const skip = screen.getByRole("link", { name: /skip to content/i });
    expect(skip).toHaveAttribute("href", "#main-content");
  });

  it("gives the active panel a heading that is the panel's name", async () => {
    stubFetch(vi);
    render(<App />);
    // Board is the default landing (spec §5).
    expect(await screen.findByRole("heading", { level: 2, name: "Board" })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel", { name: "Board" })).toBeInTheDocument();
  });

  it("sets document.title to the screen and market (spec §8.5, SC 2.4.2)", async () => {
    stubFetch(vi);
    render(<App />);
    await screen.findAllByText("2026-08-04");
    expect(document.title).toBe("Board · IDX · Screening Dashboard");

    act(() => screen.getByRole("radio", { name: "US" }).click());
    await waitFor(() => expect(document.title).toBe("Board · US · Screening Dashboard"));
  });
});

// ── The permanent regime band (spec §3.3 / §4.9) ─────────────────────────────

describe("the shell — regime band", () => {
  it("shows state, sizing posture in words, breadth and as-of date", async () => {
    stubFetch(vi, {
      regime: (m) =>
        regimeResponse({ market: m, state: "FRIENDLY", posture: "full size", breadth: 0.5 }),
    });
    render(<App />);
    const band = await screen.findByLabelText(/IDX regime/i);
    expect(band).toHaveTextContent(/FRIENDLY/);
    expect(band).toHaveTextContent(/full size/); // words, not a number
    expect(band).toHaveTextContent(/50%/);
    expect(band).toHaveTextContent("2026-08-04");
  });

  it("shows an undefined regime as warming up, with no posture", async () => {
    stubFetch(vi, {
      regime: (m) =>
        regimeResponse({ market: m, state: null, posture: null, breadth: null }),
    });
    render(<App />);
    const band = await screen.findByLabelText(/IDX regime/i);
    expect(band).toHaveTextContent(/undefined|warming up/i);
    expect(band).not.toHaveTextContent(/full size|reduced|sit out/);
  });

  it("shows no regime band before the first run has published a session", async () => {
    stubFetch(vi, {
      runs: (m) => runsResponse({ market: m, latest: null, runs: [], universe_size: null }),
      regime: (m) => regimeResponse({ market: m, session: null, state: null, posture: null, breadth: null }),
    });
    render(<App />);
    await screen.findByText(/No run yet for IDX/);
    expect(screen.queryByLabelText(/IDX regime/i)).not.toBeInTheDocument();
  });
});

// ── The run-status banner (spec §3.3, §8.7) ──────────────────────────────────

describe("the shell — run-status banner", () => {
  it("stays absent on a healthy night", async () => {
    stubFetch(vi);
    render(<App />);
    await screen.findAllByText("2026-08-04");
    expect(screen.queryByText(/quarantined|Running tonight|run failed/i)).not.toBeInTheDocument();
  });

  it("banners a quarantined latest run while still serving the last good session", async () => {
    stubFetch(vi, {
      runs: (m) =>
        runsResponse({
          market: m,
          latest: runRecord({ session: "2026-08-04" }),
          runs: [
            runRecord({ session: "2026-08-05", status: "quarantined", symbols_resolved: 50 }),
            runRecord({ session: "2026-08-04" }),
          ],
        }),
    });
    render(<App />);
    expect(await screen.findByRole("status")).toHaveTextContent(/quarantined|last good/i);
    expect(screen.getAllByText("2026-08-04").length).toBeGreaterThan(0);
  });

  it("says a run failed with a polite status, not the app's single alert", async () => {
    // A crashed run publishes nothing and clears `running`; without saying so the
    // shell kicks a run into the same wall on every open, in silence. It is a
    // status, not an alert — the single alert is reserved for an identity-read
    // failure (spec §8.7 / §11.7).
    stubFetch(vi, {
      runs: (m) =>
        runsResponse({
          market: m,
          latest: null,
          runs: [],
          universe_size: null,
          run_due: true,
          run_error: "universe already has rows",
        }),
    });
    render(<App />);
    expect(await screen.findByRole("status")).toHaveTextContent(
      /IDX run failed: universe already has rows/,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/No run yet for IDX/)).not.toBeInTheDocument();
  });

  it("raises the single role=alert when the identity read cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not reach the backend/);
  });
});

// ── Run-on-open lifecycle (spec §3.6) ────────────────────────────────────────

describe("the shell — run-on-open lifecycle", () => {
  it("kicks a run when the last final session is missing, then polls to published", async () => {
    vi.useFakeTimers();
    const okJson = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
    const post = vi.fn();
    let getCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (url.includes("/api/runs/") && opts?.method === "POST") {
          post();
          return okJson(runTriggerResponse({ market: "IDX", triggered: true, running: true }));
        }
        if (url.includes("/api/runs/")) {
          getCount += 1;
          if (getCount === 1)
            return okJson(runsResponse({ market: "IDX", run_due: true, running: false }));
          if (getCount === 2)
            return okJson(runsResponse({ market: "IDX", run_due: true, running: true }));
          return okJson(
            runsResponse({
              market: "IDX",
              latest: runRecord({ session: "2026-08-05" }),
              runs: [runRecord({ session: "2026-08-05" })],
              run_due: false,
              running: false,
            }),
          );
        }
        return okJson(regimeResponse({ market: "IDX" }));
      }),
    );
    try {
      render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(post).toHaveBeenCalledTimes(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(screen.getByRole("status")).toHaveTextContent(/Running tonight's IDX/i);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(screen.getByText("2026-08-05")).toBeInTheDocument();
      expect(screen.queryByText(/Running tonight's IDX/i)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ── The URL contract (spec §3.5, §9.3) ───────────────────────────────────────

describe("the shell — the URL contract", () => {
  it("navigates on a tab click, writing the tab to the bar and swapping the panel", async () => {
    stubFetch(vi);
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Board" });
    // A cold open is bare `/` — defaults are omitted (spec §3.5).
    expect(window.location.search).toBe("");

    act(() => screen.getByRole("tab", { name: "Leaders" }).click());

    expect(await screen.findByRole("heading", { level: 2, name: "Leaders" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Leaders" })).toHaveAttribute("aria-selected", "true");
    expect(window.location.search).toBe("?tab=leaders");
  });

  it("switches market on a radio click, writing it to the bar and refetching", async () => {
    const seen: string[] = [];
    const routes: ApiRoutes = { runs: (m) => (seen.push(m), runsResponse({ market: m })) };
    stubFetch(vi, routes);
    render(<App />);
    await screen.findAllByText("2026-08-04");
    expect(seen).toContain("IDX");

    act(() => screen.getByRole("radio", { name: "US" }).click());
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "US" })).toHaveAttribute("aria-checked", "true"),
    );
    expect(window.location.search).toBe("?market=US");
    await waitFor(() => expect(seen).toContain("US"));
  });

  it("a market switch resets the sector drill-down and keeps the active tab", async () => {
    // Start on the IDX Sectors drill-down for Energy.
    window.history.replaceState(null, "", "/?tab=sectors&sector=Energy");
    stubFetch(vi);
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Energy" })).toBeInTheDocument();

    act(() => screen.getByRole("radio", { name: "US" }).click());

    // Sector resets (Energy discarded), the Sectors tab survives (spec §3.4).
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "Sectors" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: "Sectors" })).toHaveAttribute("aria-selected", "true");
    expect(window.location.search).toBe("?market=US&tab=sectors");
  });

  it("back after a market switch restores the whole prior destination", async () => {
    // The case a future reader is most likely to 'fix' into a bug (spec §9.3):
    // back RESTORES a destination, it does not re-press the market control.
    window.history.replaceState(null, "", "/?tab=sectors&sector=Energy");
    stubFetch(vi);
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Energy" });

    act(() => screen.getByRole("radio", { name: "US" }).click());
    await screen.findByRole("heading", { level: 2, name: "Sectors" });
    expect(window.location.search).toBe("?market=US&tab=sectors");

    act(() => window.history.back());

    // Back returns to IDX / Sectors / Energy — sector and all.
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "Energy" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("radio", { name: "IDX" })).toHaveAttribute("aria-checked", "true");
    expect(window.location.search).toBe("?tab=sectors&sector=Energy");
  });

  it("a push announces nothing — it clears a prior popstate announcement (spec §8.8)", async () => {
    // A push is silent (spec §8.8): the clicked control already speaks through
    // its own role/name/state, so the destination region must carry only
    // history-nav destinations — never leave a stale one for the next push.
    window.history.replaceState(null, "", "/?tab=leaders");
    stubFetch(vi);
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Leaders" });

    act(() => screen.getByRole("radio", { name: "US" }).click()); // push US/Leaders
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "US" })).toHaveAttribute("aria-checked", "true"),
    );

    act(() => window.history.back()); // popstate → announces "Leaders, IDX"
    await screen.findByText("Leaders, IDX");

    act(() => screen.getByRole("tab", { name: "Board" }).click()); // push → must not announce
    await screen.findByRole("heading", { level: 2, name: "Board" });
    expect(screen.queryByText("Leaders, IDX")).not.toBeInTheDocument();
    expect(screen.queryByText("Board, IDX")).not.toBeInTheDocument();
  });

  it("a popstate announces the destination on the three axes — and nothing is asserted about focus", async () => {
    // Deliberately assert nothing about focus (spec §8.8, §9.3): a history
    // navigation moves no focus, and a later reader must not 'fix' that gap.
    window.history.replaceState(null, "", "/?tab=leaders");
    stubFetch(vi);
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Leaders" });

    act(() => screen.getByRole("radio", { name: "US" }).click()); // push US/Leaders
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "US" })).toHaveAttribute("aria-checked", "true"),
    );

    act(() => window.history.back()); // popstate → IDX/Leaders

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "IDX" })).toHaveAttribute("aria-checked", "true"),
    );
    // The destination region carries the axes, never the mechanism.
    const region = screen.getByText("Leaders, IDX");
    expect(region).toBeInTheDocument();
  });
});

describe("the shell — unhonourable URLs fall back and rewrite (spec §3.5)", () => {
  const cases: Array<{ url: string; canonical: string; heading: string }> = [
    { url: "/?market=XYZ", canonical: "", heading: "Board" }, // unknown market → default
    { url: "/?tab=workbench", canonical: "", heading: "Board" }, // dissolved screen → Board
    { url: "/?tab=sectors&sector=Nonesuch", canonical: "?tab=sectors", heading: "Sectors" }, // unknown sector → list
    { url: "/?tab=sectors&sector=", canonical: "?tab=sectors", heading: "Sectors" }, // empty sector → list
  ];

  for (const { url, canonical, heading } of cases) {
    it(`${url} → ${canonical || "/"} (the ${heading} screen)`, async () => {
      window.history.replaceState(null, "", url);
      stubFetch(vi);
      render(<App />);
      expect(
        await screen.findByRole("heading", { level: 2, name: heading }),
      ).toBeInTheDocument();
      // Rewritten via `replace` so no dead destination survives to be replayed.
      await waitFor(() => expect(window.location.search).toBe(canonical));
    });
  }
});
