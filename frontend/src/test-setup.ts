import "@testing-library/jest-dom/vitest";

// vitest-axe: one devDependency, in the harness already chosen (spec §8.10) —
// the automatic form of *a component with no accessible name is untestable, so
// it cannot ship*. Extending `expect` here makes `toHaveNoViolations` available
// to every screen suite; a suite adds one `expect(await axe(container))` line.
//
// ⚠ The caveat is part of the decision: jsdom has no layout and no computed
// colour, so axe verifies **none** of the contrast work and **none** of the
// focus ring. Those are checked once, at the token level, by a human against
// the §8.3 ratio table — not here.
import * as axeMatchers from "vitest-axe/matchers";
import { expect } from "vitest";

expect.extend(axeMatchers);
