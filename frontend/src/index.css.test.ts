import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The styling floor is CSS, and Vitest stubs every CSS import to an empty string
// under jsdom (spec §3.2) — a `?raw` suffix does not escape it either — so there
// is no module content and no computed style to assert. Read the source off disk
// and assert the token contract directly: the values a human measured in §8.3
// and the tree-shaking fix that keeps runtime-only tokens in the emitted sheet.
const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

describe("the v2 token set (spec §3.2, §8.3)", () => {
  it("pulls in Tailwind v4 CSS-first", () => {
    expect(css).toMatch(/@import\s+["']tailwindcss["']/);
  });

  it("self-hosts and applies both fonts", () => {
    // Self-hosted via @fontsource, not a CDN <link>.
    expect(css).toMatch(/@fontsource\/space-grotesk/);
    expect(css).toMatch(/@fontsource\/ibm-plex-mono/);
    // Declared as theme tokens...
    expect(css).toMatch(/--font-sans:\s*"Space Grotesk"/);
    expect(css).toMatch(/--font-mono:\s*"IBM Plex Mono"/);
    // ...and actually applied to the document.
    expect(css).toMatch(/font-family:\s*var\(--font-sans\)/);
  });

  it("opens @theme by wiping the stock colour scales", () => {
    expect(css).toMatch(/--color-\*:\s*initial/);
  });

  it("carries the darkened neutrals and semantic trio, not the reference's", () => {
    // The reference values are rejected (§8.3): these are the measured lifts.
    expect(css).toMatch(/--color-text-muted:\s*#6b665c/i);
    expect(css).toMatch(/--color-green:\s*#17703e/i);
    expect(css).toMatch(/--color-amber:\s*#8a6215/i);
    expect(css).toMatch(/--color-red:\s*#b03d26/i);
    // The reference's lighter values must not survive.
    expect(css).not.toMatch(/#8a857c/i); // old textMuted
    expect(css).not.toMatch(/#1f8a4c/i); // old green
    expect(css).not.toMatch(/#c08a2e/i); // old amber
    expect(css).not.toMatch(/#c8492f/i); // old red
  });

  it("carries the paper ground, radius, shadow and container from §3.2", () => {
    expect(css).toMatch(/--color-bg:\s*#e7e4de/i);
    expect(css).toMatch(/--color-card:\s*#ffffff/i);
    expect(css).toMatch(/--radius-card:\s*1\.125rem/);
    expect(css).toMatch(/--container-shell:\s*82\.5rem/);
    expect(css).toMatch(/--shadow-shell:/);
  });

  it("keeps the reference's 9.5px type floor", () => {
    // 9.5px = 0.59375rem — the density variant that was kept (§3.2).
    expect(css).toMatch(/--text-micro:\s*0\.59375rem/);
    expect(css).toMatch(/--text-ticker:/);
  });

  it("carries the two-tone :focus-visible ring, never :focus (spec §8.6)", () => {
    // A dark core plus a light halo, so the ring survives on the near-black
    // active seg item and on paper alike.
    expect(css).toMatch(/--color-focus-core:\s*#1c1b18/i);
    expect(css).toMatch(/--color-focus-halo:\s*#f6f4ef/i);
    // The ring lives under :focus-visible and carries both tones.
    const ring = css.match(/:focus-visible\s*\{[\s\S]*?\}/)?.[0] ?? "";
    expect(ring).toMatch(/--color-focus-halo/);
    expect(ring).toMatch(/--color-focus-core/);
    // The ring must not be keyed off a bare element `:focus` — that would
    // scatter rings on mouse clicks across a dense board. The only `:focus` use
    // is the skip link becoming visible, which carries no ring.
    expect(css).not.toMatch(/\*:focus\s*\{/);
  });

  it("zeroes transitions under prefers-reduced-motion, globally (spec §8.7)", () => {
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  });

  it("docks the chart sheet at min(560px, 90vw), fixed, with a shadow (spec §6)", () => {
    const sheet = css.match(/\.chart-sheet\s*\{[\s\S]*?\}/)?.[0] ?? "";
    // The min() is load-bearing: a fixed 560px would swallow a 200%-zoom viewport.
    expect(sheet).toMatch(/width:\s*min\(560px,\s*90vw\)/);
    expect(sheet).toMatch(/position:\s*fixed/);
    expect(sheet).toMatch(/right:\s*0/);
    expect(sheet).toMatch(/box-shadow:\s*var\(--shadow-shell\)/);
  });

  it("lays the Board out as 1fr + 384px, collapsing the rail under the sheet (spec §5.1)", () => {
    const grid = css.match(/\.board-grid\s*\{[\s\S]*?\}/)?.[0] ?? "";
    // Heroes/strip left at 1fr, the rotation rail in a fixed 384px right column.
    expect(grid).toMatch(/grid-template-columns:\s*1fr\s+384px/);
    // When the sheet is open the rail collapses to one column so the hero grid
    // keeps its two columns rather than reflowing on every open.
    const open = css.match(/\.board-grid--sheet-open\s*\{[\s\S]*?\}/)?.[0] ?? "";
    expect(open).toMatch(/grid-template-columns:\s*1fr\b/);
    // The hero grid stays two columns regardless of the rail's state.
    const hero = css.match(/\.hero-grid\s*\{[\s\S]*?\}/)?.[0] ?? "";
    expect(hero).toMatch(/grid-template-columns:\s*repeat\(2,\s*1fr\)/);
  });

  it("closes the tree-shaking trap: sector + regime scales live in a plain :root", () => {
    // Tailwind v4 tree-shakes @theme vars no utility class mentions. The sector
    // scale and regime pairs are read only from a runtime var(), so they must be
    // restated in a plain :root to survive into the emitted sheet (§3.2, map #59).
    const root = css.match(/:root\s*\{[\s\S]*?\}/g)?.join("\n") ?? "";
    expect(root).toMatch(/--color-sector-technology:/);
    expect(root).toMatch(/--color-sector-energy:/);
    expect(root).toMatch(/--color-regime-ok:/);
    expect(root).toMatch(/--color-regime-stop:/);
  });
});

// A class ships in a component but has no matching rule → it renders unstyled,
// which reads as breakage rather than as a plain aesthetic (issue #95). Match the
// class as a whole selector token: `.tab` must not be satisfied by `.tab-row`, so
// the class name may not be followed by a word char or a hyphen.
function hasRule(className: string): boolean {
  return new RegExp(`\\.${className}(?![\\w-])`).test(css);
}

describe("the v2 shell, Leaders and Sectors are styled (issue #95)", () => {
  // Every class below is referenced by a component and, before #95, matched no
  // rule in index.css. The shell chrome and two screens rendered as unstyled
  // text runs; the ARIA was correct throughout, so this is purely the visual
  // layer. Grouped by the component that ships the markup.
  const SHELL_CLASSES = [
    "tab-row", "tab", "market-control", "market-item", "shell-header",
    "shell-header-row", "shell-product", "shell-asof", "shell-loading",
    "regime-banner", "run-status-dismiss", "identity-error",
    "empty-state", "no-run-yet", "screen-placeholder",
  ];
  const LEADERS_CLASSES = [
    "leaders-controls", "seg-item", "view", "ticker-search", "sector-select",
    "adr-toggle", "sort-button", "leaders-table", "leaders-grid",
    "leader-card", "leader-card-head", "leader-card-facts",
    "leaders-summary", "leaders-skeleton", "badge-new-to-leaders",
  ];
  const SECTORS_CLASSES = [
    "sector-detail", "member-table", "member-pctile", "member-decile",
    "lookback-item", "top-decile-toggle", "decile-badge-empty",
    "breadcrumb-current", "rank", "return-value", "share", "shape",
  ];

  it.each(SHELL_CLASSES)("styles the shell class .%s", (c) => {
    expect(hasRule(c)).toBe(true);
  });
  it.each(LEADERS_CLASSES)("styles the Leaders class .%s", (c) => {
    expect(hasRule(c)).toBe(true);
  });
  it.each(SECTORS_CLASSES)("styles the Sectors class .%s", (c) => {
    expect(hasRule(c)).toBe(true);
  });

  it("covers exactly the 42 classes the audit named", () => {
    expect(
      SHELL_CLASSES.length + LEADERS_CLASSES.length + SECTORS_CLASSES.length,
    ).toBe(42);
  });
});
