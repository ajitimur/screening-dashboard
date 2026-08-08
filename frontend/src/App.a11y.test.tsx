import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import App from "./App";
import { stubFetch } from "./api/fixtures";

// The chart canvas jsdom cannot render; stub the library so the shell mounts.
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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// The first screen suite to carry the automatic a11y check (spec §8.10). It is
// wired off the shared fixture module: `stubFetch` serves the whole contract,
// so the shell renders a populated tree and axe sees real markup.
//
// ⚠ jsdom has no layout or computed colour — axe verifies neither contrast nor
// the focus ring here; those are checked once at token level by a human.
describe("the shell screen — accessibility", () => {
  it("renders with no axe violations", async () => {
    stubFetch(vi);
    render(<App />);
    await screen.findAllByText("2026-08-04"); // wait for the first paint to settle

    // color-contrast is disabled: jsdom has no computed colour, so axe cannot
    // verify it here — contrast is checked once at token level by a human
    // against the §8.3 ratio table (spec §8.10). Leaving the rule on only emits
    // a canvas-not-implemented warning and asserts nothing.
    const results = await axe(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
