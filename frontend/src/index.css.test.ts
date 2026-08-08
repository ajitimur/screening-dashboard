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
