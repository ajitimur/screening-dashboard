import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { useCallback, useRef, useState } from "react";
import { FilterEmpty, NightEmpty, Panel, useBodyRead } from "./Panel";

afterEach(cleanup);

// A deferred promise so a test can hold a body read in flight: the loading and
// market-switch skeletons (spec §7.3/§7.6) are only observable while pending.
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// One panel driven by `useBodyRead`, with a market control so a test can trigger
// the mid-flight switch. The fetcher is held in a ref so its identity is stable
// across renders (the hook takes it as an effect dependency).
function Harness({ fetcher }: { fetcher: (market: string) => Promise<string> }) {
  const ref = useRef(fetcher);
  ref.current = fetcher;
  const stable = useCallback((m: string) => ref.current(m), []);
  const [market, setMarket] = useState("IDX");
  const read = useBodyRead(market, stable);
  return (
    <>
      <button onClick={() => setMarket("US")}>switch</button>
      <Panel
        label="Rotation"
        read={read}
        skeleton={<div data-testid="skeleton" style={{ height: 200 }} />}
      >
        {(data) => <p>{data}</p>}
      </Panel>
    </>
  );
}

// ── The body read (spec §7.3 / §7.6) ─────────────────────────────────────────

describe("useBodyRead / Panel — the body-owned state matrix", () => {
  it("paints when ready, and not before (progressive paint, spec §7.3)", async () => {
    const d = deferred<string>();
    render(<Harness fetcher={() => d.promise} />);

    // Before the read resolves: the skeleton in an aria-busy frame, no values.
    expect(screen.getByTestId("skeleton")).toBeInTheDocument();
    expect(screen.getByLabelText("Rotation")).toHaveAttribute("aria-busy", "true");

    await act(async () => d.resolve("IDX rotation"));

    expect(await screen.findByText("IDX rotation")).toBeInTheDocument();
    expect(screen.getByLabelText("Rotation")).not.toHaveAttribute("aria-busy");
  });

  it("a market switch blanks the values and keeps the frame — never mixed markets (spec §7.6)", async () => {
    const reads = [deferred<string>(), deferred<string>()];
    let call = 0;
    render(<Harness fetcher={() => reads[call++].promise} />);

    await act(async () => reads[0].resolve("IDX rotation"));
    await screen.findByText("IDX rotation");

    // Switch to US while the second read is still in flight.
    act(() => screen.getByRole("button", { name: "switch" }).click());

    // The old market's values are gone IMMEDIATELY — never shown under the new
    // label, even for a frame (the one state that could produce a wrong trade)…
    expect(screen.queryByText("IDX rotation")).not.toBeInTheDocument();
    // …the frame survives and the skeleton is busy at its real dimensions.
    expect(screen.getByLabelText("Rotation")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("skeleton")).toBeInTheDocument();

    await act(async () => reads[1].resolve("US rotation"));
    expect(await screen.findByText("US rotation")).toBeInTheDocument();
  });

  it("a body-read failure posts a polite notice, never an alert, and keeps the frame (spec §7.1)", async () => {
    const d = deferred<string>();
    render(<Harness fetcher={() => d.promise} />);

    await act(async () => d.reject(new Error("rotation read failed")));

    expect(await screen.findByRole("status")).toBeInTheDocument();
    // A panel notice is deliberately NOT an alert — the single alert is the
    // shell's, for identity reads (spec §7.1 / §8.7).
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // The panel collapses only itself: its frame survives (spec §7.1).
    expect(screen.getByLabelText("Rotation")).toBeInTheDocument();
  });

  it("panels paint independently — the fast one does not wait on the slow one (spec §7.3)", async () => {
    const fast = deferred<string>();
    const slow = deferred<string>();
    function Two() {
      const f = useCallback((_m: string) => fast.promise, []);
      const s = useCallback((_m: string) => slow.promise, []);
      const rf = useBodyRead("IDX", f);
      const rs = useBodyRead("IDX", s);
      return (
        <>
          <Panel label="Fast" read={rf} skeleton={<div>fast-skeleton</div>}>
            {(d) => <p>{d}</p>}
          </Panel>
          <Panel label="Slow" read={rs} skeleton={<div>slow-skeleton</div>}>
            {(d) => <p>{d}</p>}
          </Panel>
        </>
      );
    }
    render(<Two />);

    await act(async () => fast.resolve("fast done"));

    // Fast has painted while slow is still busy — no whole-screen gate (§7.3).
    expect(await screen.findByText("fast done")).toBeInTheDocument();
    expect(screen.getByText("slow-skeleton")).toBeInTheDocument();
    expect(screen.getByLabelText("Slow")).toHaveAttribute("aria-busy", "true");

    await act(async () => slow.resolve("slow done"));
    expect(await screen.findByText("slow done")).toBeInTheDocument();
  });
});

// ── The two empty registers (spec §7.4) ──────────────────────────────────────

describe("the empty registers", () => {
  it("a night-inflicted empty states the fact and never apologises", () => {
    render(
      <NightEmpty>No candidates tonight — no name is sitting in a valid base.</NightEmpty>,
    );
    const el = screen.getByText(/No candidates tonight/);
    expect(el).toBeInTheDocument();
    // Prose that never apologises, and not the error treatment (spec §7.4).
    expect(el.textContent).not.toMatch(/sorry|apolog|error|failed|unavailable/i);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("a filter-inflicted empty carries the offending chip and a clear action (spec §7.4)", () => {
    const onClear = vi.fn();
    render(
      <FilterEmpty chip="ADR ≥ 4%" onClear={onClear}>
        No rows above the sub-4% ADR floor.
      </FilterEmpty>,
    );
    // The offending chip is named…
    expect(screen.getByText("ADR ≥ 4%")).toBeInTheDocument();
    // …and the click that recovers it is on screen (the one rule, spec §7.4).
    const clear = screen.getByRole("button", { name: /clear filter/i });
    act(() => clear.click());
    expect(onClear).toHaveBeenCalledTimes(1);
    // A recoverable empty is not the error treatment either.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the matrix markup with no axe violations (spec §8.10)", async () => {
    // The new user-facing states a screen will render — the polite notice and
    // both empty registers — carry the automatic a11y check the shell suite does
    // (color-contrast disabled: jsdom has no computed colour, §8.10).
    // The empties render inside a screen's landmark in the app; mirror that here
    // so the `region` rule sees them contained, as they always are in use.
    render(
      <main>
        <Panel label="Rotation" read={{ status: "error", message: "x" }} skeleton={null}>
          {() => null}
        </Panel>
        <NightEmpty>No candidates tonight — no name is sitting in a valid base.</NightEmpty>
        <FilterEmpty chip="ADR ≥ 4%" onClear={() => {}}>
          No rows above the sub-4% ADR floor.
        </FilterEmpty>
      </main>,
    );
    const results = await axe(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
