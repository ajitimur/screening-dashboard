// Teach vitest's `expect` about the matcher `test-setup.ts` extends it with, so
// `expect(await axe(container)).toHaveNoViolations()` type-checks in a suite.
import "vitest";
import type { AxeMatchers } from "vitest-axe/matchers";

declare module "vitest" {
  interface Assertion extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
