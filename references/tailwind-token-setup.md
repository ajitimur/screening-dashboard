# q-scanner's design tokens as a Tailwind theme (Vite + React 18 + TS)

Research note for issue #55. **Reference only** — nothing here has been installed or applied.
Every claim is cited to an official Tailwind/Fontsource/Vitest doc URL or to a `file:line` in
`/Users/ajitimur/Projects/q-scanner-v2` (read-only source repo) or this repo's `frontend/`.

Researched 2026-08-06. Tailwind docs pages were fetched live; the docs site self-identifies as
**v4.3** and the npm registry reports `tailwindcss@4.3.3` as `latest`
(`https://registry.npmjs.org/tailwindcss` → `dist-tags.latest = 4.3.3`; a `v3-lts` tag exists at
`3.4.19`).

---

## 0. Where this repo stands today

Read from `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/src/`:

| Fact | Value |
| ---- | ----- |
| Vite | `^5.4.2` |
| React / React DOM | `^18.3.1` |
| TypeScript | `^5.5.4` |
| Plugin | `@vitejs/plugin-react ^4.3.1` |
| Test runner | `vitest ^2.0.5` + jsdom, config shared with Vite |
| CSS framework | **none** |
| Stylesheets | **none** — `find frontend -name "*.css"` outside `node_modules` returns nothing |
| Inline `style=` props | **zero** — `grep -rn "style=" frontend/src/` returns nothing |
| Existing `className` usage | semantic hooks only: `run-progress`, `run-failed`, `empty-state`, `quarantine-banner`, `as-of`, `universe-size`, `regime-banner` (`frontend/src/App.tsx`) |

So the frontend is **completely unstyled**. Those `className` strings resolve to nothing — they are
test/future hooks, not styles. `frontend/src/main.tsx` imports no CSS at all.

That is the ideal starting point: no legacy stylesheet to reconcile, no inline-style convention to
unpick, no preprocessor or CSS Modules to unwind. Contrast with q-scanner-v2, which is styled
**entirely** through inline `CSSProperties` objects exported from `theme.ts` — no framework there
either. The migration is therefore additive here and a rewrite there.

---

## 1. Which version, and how it installs here

**Target Tailwind v4.** It is current, and for a Vite project the docs prescribe the dedicated
Vite plugin, not PostCSS.

Documented current path — <https://tailwindcss.com/docs/installation/using-vite>:

```bash
npm install tailwindcss @tailwindcss/vite
```

```ts
// vite.config.ts
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss()],
});
```

```css
/* the one CSS entry file */
@import "tailwindcss";
```

The v3 path is the *old* one — v3 docs (<https://v3.tailwindcss.com/docs/guides/vite>) require
`npm install -D tailwindcss@3 postcss autoprefixer`, `npx tailwindcss init -p`, a
`tailwind.config.js` with a `content` glob, and `@tailwind base; @tailwind components;
@tailwind utilities;` in the CSS. v4 needs none of that: no `postcss.config.js`, no
`autoprefixer`, no `content` array (v4 auto-detects sources), no `postcss-import`
(<https://tailwindcss.com/docs/upgrade-guide> — "in v4 imports and vendor prefixing is now
handled for you automatically, so you can remove `postcss-import` and `autoprefixer`"). The same
guide says explicitly: "If you're using Vite, we recommend migrating from the PostCSS plugin to
our new dedicated Vite plugin for improved performance and the best developer experience."

### Version constraints against this repo

| Constraint | Source | Verdict |
| --- | --- | --- |
| `@tailwindcss/vite` peer dep: `vite: ^5.2.0 \|\| ^6 \|\| ^7 \|\| ^8` | `https://registry.npmjs.org/@tailwindcss/vite` (4.3.3 manifest) | This repo has `vite ^5.4.2` (`frontend/package.json`) — **satisfied**, no Vite upgrade needed. |
| React version | Tailwind has no React peer dep; it ships CSS only | React 18.3.1 is irrelevant to Tailwind. **Fine.** |
| vitest 2.0.5 | Vitest reads the same `vite.config.ts` (this repo uses `defineConfig` from `vitest/config`, `frontend/vite.config.ts:1`) so the plugin is active in tests too | Fine — see §5. |
| Browser floor | <https://tailwindcss.com/docs/compatibility> — "Chrome 111, Safari 16.4, Firefox 128"; upgrade guide: "If you need to support older browsers, stick with v3.4" | Internal trading dashboard → not a blocker. This is the *only* reason to consider v3. |
| Node | <https://tailwindcss.com/docs/upgrade-guide> — the `@tailwindcss/upgrade` tool "requires Node.js 20 or higher" (that's the codemod tool; a greenfield install has no v3 to migrate) | N/A here — nothing to upgrade, this repo has no Tailwind at all. |

Also from <https://tailwindcss.com/docs/compatibility>: do **not** pair v4 with Sass/Less/Stylus,
and CSS Modules are "not recommended" (Tailwind re-runs per module, and `@theme` context is lost).
Neither is in use in `frontend/`, so nothing to unwind.

### Setup steps for this repo, concretely

1. `cd frontend && npm install tailwindcss @tailwindcss/vite`
2. Add `tailwindcss()` to the `plugins` array in `frontend/vite.config.ts` (alongside `react()`).
3. Create `frontend/src/index.css` (the repo currently has **no CSS file at all** — verified: no
   `*.css` outside `node_modules`).
4. `import "./index.css";` at the top of `frontend/src/main.tsx`.
5. Fonts: `npm install @fontsource/space-grotesk @fontsource/ibm-plex-mono` (see §3).

---

## 2. Declaring the tokens: CSS-first `@theme`, not a JS config

In v4 the theme is declared in CSS with `@theme`, and each variable both *is* a CSS custom
property and *generates utilities* (<https://tailwindcss.com/docs/theme>): "Theme variables are
special CSS variables defined using the `@theme` directive that influence which utility classes
exist in your project." Declaring `--color-mint-500` yields `bg-mint-500`, `text-mint-500`, etc.,
**and** `var(--color-mint-500)` usable from inline styles.

Namespaces relevant to q-scanner (<https://tailwindcss.com/docs/theme#theme-variable-namespaces>):
`--color-*` (`bg-*`/`text-*`/`border-*`), `--font-*` (`font-*`), `--radius-*` (`rounded-*`),
`--shadow-*` (`shadow-*`), `--container-*` (`max-w-*`), `--text-*` (`text-<size>`),
`--tracking-*` (`tracking-*`).

JS config still works but is legacy: "JavaScript config files are still supported for backward
compatibility, but they are no longer detected automatically in v4" — you must opt in with
`@config "../../tailwind.config.js"`, and `corePlugins`, `safelist` and `separator` are **not
supported** there any more (<https://tailwindcss.com/docs/functions-and-directives>). Use
`@theme`. Note the dropped `safelist` option — the v4 replacement is `@source inline()` (§4).

### The token declaration (copy-pasteable)

Sources for the values: `/Users/ajitimur/Projects/q-scanner-v2/web/src/theme.ts:3-35,47-49,62-85`,
`/Users/ajitimur/Projects/q-scanner-v2/web/index.html:8-19`,
`/Users/ajitimur/Projects/q-scanner-v2/web/src/App.tsx:78`.

```css
/* frontend/src/index.css */
@import "tailwindcss";

/* Self-hosted fonts — see §3. Fontsource CSS may also be imported from main.tsx instead. */
@import "@fontsource/space-grotesk/400.css";
@import "@fontsource/space-grotesk/500.css";
@import "@fontsource/space-grotesk/600.css";
@import "@fontsource/space-grotesk/700.css";
@import "@fontsource/ibm-plex-mono/400.css";
@import "@fontsource/ibm-plex-mono/500.css";
@import "@fontsource/ibm-plex-mono/600.css";

@theme {
  /* ---- fonts (theme.ts:3-4) ---- */
  --font-sans: "Space Grotesk", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", monospace;

  /* ---- paper palette (theme.ts:6-27) ---- */
  --color-bg: #e7e4de;
  --color-surface: #f6f4ef;
  --color-surface-alt: #f9f6f0;
  --color-card: #fff;
  --color-border: #e8e2d8;
  --color-border-strong: #d8cbb6;
  --color-text: #1c1b18;
  --color-text-muted: #8a857c;
  --color-text-faint: #a09a8e;
  --color-chip: #f2eee6;
  --color-seg-bg: #ece7dd;
  --color-track: #efeae0;
  --color-hover: #faf7f1;
  --color-hover-accent: #c67139;
  --color-underline: #b3ab9d;
  --color-scrollbar-thumb: #d8cfbf;   /* index.html:19 */

  /* ---- verdict semantics (theme.ts:22-24, 44-55) ---- */
  --color-green: #1f8a4c;
  --color-amber: #c08a2e;
  --color-red: #c8492f;
  --color-teal: #0f766e;
  --color-teal-dark: #0b5a54;

  --color-verdict-ready: #1f7a45;
  --color-verdict-ready-bg: #e7f2ea;
  --color-verdict-wait: #a9781f;
  --color-verdict-wait-bg: #f6ecd8;
  --color-verdict-no: #b0402a;
  --color-verdict-no-bg: #f6e3dd;

  /* ---- sector scale (theme.ts:62-85) ----
         The source map has 21 keys but only 12 distinct hues: it carries aliases for
         short labels ("Comm Svcs") and for IDX-IC's own classification (docs/adr/0002).
         Declared once per hue; the alias→hue collapse stays in TypeScript. */
  --color-sector-technology: #2f7d5b;         /* Technology */
  --color-sector-financials: #2a6f97;         /* Financial Services | Financials */
  --color-sector-industrials: #b5651d;        /* Industrials */
  --color-sector-communication: #8e5572;      /* Communication Services | Comm Svcs
                                                 | IDX Transportation & Logistics */
  --color-sector-consumer-cyclical: #c9843e;  /* Consumer Cyclical(s) | Cons Cyclical */
  --color-sector-healthcare: #4c9a8f;         /* Healthcare */
  --color-sector-utilities: #7a8a5e;          /* Utilities */
  --color-sector-energy: #a8453a;             /* Energy */
  --color-sector-materials: #9c7a3c;          /* Basic Materials | Materials */
  --color-sector-consumer-defensive: #6b7d8a; /* Consumer Defensive | Cons Defensive
                                                 | IDX Consumer Non-Cyclicals */
  --color-sector-real-estate: #7d6b8a;        /* Real Estate | IDX Properties & Real Estate */
  --color-sector-infrastructures: #5f7f9c;    /* IDX Infrastructures only */

  /* ---- structure (App.tsx:78) ---- */
  --radius-card: 1.125rem;                              /* 18px */
  --shadow-shell: 0 30px 70px rgb(40 34 24 / 0.20);
  --container-shell: 82.5rem;                           /* 1320px → max-w-shell */

  /* ---- small type scale seen throughout theme.ts ---- */
  --text-micro: 0.594rem;   /* 9.5px — statLabel / verdict badge, theme.ts:52,144 */
  --tracking-badge: 0.04em; /* theme.ts:52 */
  --tracking-label: 0.05em; /* theme.ts:144 */
}
```

Then `bg-bg`, `bg-surface`, `text-text-muted`, `border-border-strong`, `rounded-card`,
`shadow-shell`, `max-w-shell`, `font-sans`, `font-mono`, `text-micro` all exist as utilities.

### Referencing them from class names

The namespace prefix drops; the rest becomes the utility suffix. q-scanner's shell
(`App.tsx:78` — a single inline style object) becomes:

```tsx
<div className="bg-bg font-sans text-text">
  <div className="w-shell max-w-full overflow-hidden rounded-card bg-surface shadow-shell
                  flex flex-col">
    <span className="font-mono text-green">+12.4%</span>
    <span className="text-text-muted">as of …</span>
    <a className="text-teal hover:text-teal-dark">…</a>
  </div>
</div>
```

Theme variables are simultaneously plain CSS variables, so `var(--color-teal)` works in handwritten
CSS and in inline styles — the docs show `style="background-color: var(--color-mint-500)"` directly
(<https://tailwindcss.com/docs/theme>). That dual nature is exactly what makes Pattern B in §4 work.

Note `@theme inline` is **not** needed here. The docs reserve it for the case where a theme
variable's value is *another* variable ("Without using `inline`, your utility classes might resolve
to unexpected values because of how variables are resolved in CSS" —
<https://tailwindcss.com/docs/theme>). Every value above is a literal hex or length.

**Two decisions worth flagging.**

- `--font-sans` / `--font-mono` here *override* Tailwind's defaults, so every unprefixed
  `font-sans` in the app picks up Space Grotesk. The docs support redefining defaults: "Override
  default theme variables by redefining them" (<https://tailwindcss.com/docs/theme>).
- Keeping Tailwind's stock colour palette alongside the custom one is the default. If you want
  *only* q-scanner's colours to exist (so a stray `bg-red-500` fails loudly), the docs give
  `--color-*: initial;` as the first line inside `@theme`: "all of the default utilities that use
  that namespace (like `bg-red-500`) will be removed, and only your custom values will be
  available." Recommended here — q-scanner's `red`/`green`/`amber` names would otherwise collide
  confusingly with Tailwind's scales.

### Base styles (the non-token half of `index.html`)

`/Users/ajitimur/Projects/q-scanner-v2/web/index.html:8-19` is plain global CSS. In v4 that goes in
a `@layer base` block in the same file (`@layer` is a supported directive —
<https://tailwindcss.com/docs/functions-and-directives>):

```css
@layer base {
  :root { color-scheme: light; }
  body { background: var(--color-bg); font-family: var(--font-sans); }
  a { color: var(--color-teal); }
  a:hover { color: var(--color-teal-dark); }
  input, select, button { font-family: var(--font-sans); }
  select { appearance: none; -webkit-appearance: none; }
  input:focus-visible, select:focus-visible {
    outline: 2px solid var(--color-teal);
    outline-offset: 1px;
  }
  ::selection { background: rgb(198 113 57 / 0.2); }   /* hover-accent @ 20% */
  button { font: inherit; cursor: pointer; }
  .qs-scroll::-webkit-scrollbar { height: 9px; width: 9px; }
  .qs-scroll::-webkit-scrollbar-thumb {
    background: var(--color-scrollbar-thumb);
    border-radius: 6px;
  }
}
```

`* { box-sizing: border-box }` and `body { margin: 0 }` (index.html:9-10) are already handled by
Tailwind's Preflight, which `@import "tailwindcss"` includes.

---

## 3. Self-hosted `@fontsource/*` fonts

Fontsource's own docs (<https://fontsource.org/docs/getting-started/install>) say: install the
package, then `import "@fontsource/open-sans/300.css";` per weight — "A single import statement
will load **one** font file", and italics are separate. After that you "reference it in your CSS
stylesheets, CSS Modules, or CSS-in-JS using the font family name."

q-scanner imports seven weight files from JS
(`/Users/ajitimur/Projects/q-scanner-v2/web/src/main.tsx:1-7`) against
`@fontsource/space-grotesk` and `@fontsource/ibm-plex-mono`
(`/Users/ajitimur/Projects/q-scanner-v2/web/package.json:12-13`; both are at `5.3.0` latest on npm
today). Copy that list verbatim — either as JS imports in `frontend/src/main.tsx` or as `@import`
lines in `index.css` (shown in §2).

Wiring into the theme is then just the family name, per Tailwind's font-family docs
(<https://tailwindcss.com/docs/font-family>): `@theme { --font-display: "Oswald", sans-serif; }`.
Fontsource emits the `@font-face` rules, so you do **not** need to write `@font-face` yourself —
that section of the docs is for raw `.woff2` files.

Ordering caveat from the same page: remote `@import url(...)` must come before `@import
"tailwindcss"`. That rule is about *URL* imports and browser `@import` ordering. Fontsource is a
bundled package import, so either placement works; if you put the Fontsource `@import`s in the CSS
file, put them after `@import "tailwindcss"` only if you're comfortable — the safe, unambiguous
option is importing them from `main.tsx` exactly as q-scanner does.

Two caveats worth checking at implementation time, neither documented as a blocker: Tailwind
v4 has no `content`/purge step for `@font-face`, so unused weights are shipped as-is — keep the
import list to weights actually used (q-scanner uses 400/500/600/700 sans, 400/500/600 mono).

---

## 4. Data-driven values — the part that decides the migration

Tailwind's constraint, verbatim
(<https://tailwindcss.com/docs/detecting-classes-in-source-files>):

> "Since Tailwind scans your source files as plain text, it has no way of understanding string
> concatenation or interpolation in the programming language you're using."
> … "In the example above, the strings `text-red-600` and `text-green-600` do not exist, so
> Tailwind will not generate those classes."

So `` className={`bg-[${sectorColor(name)}]`} `` **will not work**, ever. There are three
sanctioned escapes.

### Pattern A — map to complete class names (docs' primary recommendation)

Same page: "Always use complete class names", with this example:

```jsx
function Button({ color, children }) {
  const colorVariants = {
    blue: "bg-blue-600 hover:bg-blue-500 text-white",
    red: "bg-red-500 hover:bg-red-400 text-white",
    yellow: "bg-yellow-300 hover:bg-yellow-400 text-black",
  };
  return <button className={`${colorVariants[color]} ...`}>{children}</button>;
}
```

The keys are runtime; the *values* are literal strings in source, so the scanner sees them.
Works only when the value set is **closed and known at build time**.

### Pattern B — CSS variable set by inline `style`, referenced by a utility

From <https://tailwindcss.com/docs/styling-with-utility-classes>, verbatim:

> "Another useful pattern is setting CSS variables based on dynamic sources using inline styles,
> then referencing those variables with utility classes:"

```jsx
export function BrandedButton({ buttonColor, buttonColorHover, textColor, children }) {
  return (
    <button
      style={{
        "--bg-color": buttonColor,
        "--bg-color-hover": buttonColorHover,
        "--text-color": textColor,
      }}
      className="bg-(--bg-color) text-(--text-color) hover:bg-(--bg-color-hover) ..."
    >
      {children}
    </button>
  );
}
```

`bg-(--x)` is shorthand for `bg-[var(--x)]`, "automatically adds the `var()` function"
(<https://tailwindcss.com/docs/adding-custom-styles>). This is the **only** pattern that handles a
genuinely open value set, and it is what the docs put forward for exactly this situation.

### Pattern C — safelist with `@source inline()`

Same detection page:

```css
@source inline("{hover:,focus:,}underline");
@source inline("{hover:,}bg-red-{50,{100..900..100},950}");
```

Brace expansion generates variants and numeric ranges; `@source not inline(...)` excludes.
This is v4's replacement for v3's `safelist` config key (which `@config` no longer honours —
<https://tailwindcss.com/docs/functions-and-directives>). Use it when the class strings are
computed but the *set* is closed and you don't want to spell them out in JSX.

### Arbitrary values, and their limit

`bg-[#bada55]`, `top-[117px]`, `[--scroll-offset:56px] lg:[--scroll-offset:44px]`
(<https://tailwindcss.com/docs/adding-custom-styles>). Underscores become spaces at build time.
**The limit is that these are still build-time literals** — the square-bracket content must appear
verbatim in a source file. Arbitrary values solve "value not in my theme"; they do *not* solve
"value not known until the API responds".

### Verdict per q-scanner case

| q-scanner case | Source | Value set | Use |
| --- | --- | --- | --- |
| **Sector colour** `sectorColor(name)` keyed by an API sector string, with a `?? colors.textFaint` fallback | `theme.ts:111-113`, map at `62-85` | Closed *today* (21 keys across two classification schemes) but keyed by a **backend string** — a new sector or a renamed one appears at runtime, and the fallback proves the author expected misses | **Pattern B.** Keep the TS map as the source of truth returning a colour string; set `style={{ "--sector": sectorColor(name) }}` and use `bg-(--sector)` / `text-(--sector)`. Pattern A would silently drop any sector the map didn't anticipate — and the existing fallback branch would have no class to emit. |
| **Verdict colour** chosen from a payload field | `theme.ts:29-35, 37-55` — `normVerdict` already collapses every input to exactly `READY \| WAIT \| NO` | **Closed, 3 members**, normalised in code | **Pattern A.** `const verdictClasses = { READY: "text-verdict-ready bg-verdict-ready-bg", WAIT: "…", NO: "…" }` indexed by `normVerdict(v) ?? "NO"`. Static classes, no inline style, full variant support (`hover:`, `dark:`) — strictly better than B here. |
| **Bar width** from a percentage | `theme.ts:119-124` — `width: \`${clamp(pct)}%\`` | **Continuous** — infinite set | **Inline `style` for the width, full stop.** Neither A nor C can enumerate it and `w-[…]` needs a literal. Either keep `style={{ width }}` and put the static bits (`block h-full rounded-[3px]`) in classes, or use Pattern B (`style={{ "--w": pct + "%" }}` + `w-(--w)`) if you want the width to participate in variants. The colour argument of `bar(color, pct)` is a sector/verdict colour → Pattern B as above. |

**Bottom line for the migration:** the large runtime-coloured surface is *not* a blocker, but it
does mean q-scanner's `theme.ts` helpers do not disappear — they change return type from
`CSSProperties` to either a class-name string (verdicts) or a `{ "--sector": "#…" }` style object
(sectors). Budget for rewriting `verdictBadgeStyle`, `verdictDotStyle`, `sectorColor`, `bar`,
`segItem`, `tickerStyle`, `statMono` (`theme.ts:44-148`) rather than deleting them.

### Worked examples

**Verdict badge (Pattern A)** — replaces `verdictBadgeStyle` (`theme.ts:44-55`). Six full class
strings, all literal in source, all visible to the scanner. No safelist needed.

```tsx
const VERDICT_CLASSES = {
  READY: "text-verdict-ready bg-verdict-ready-bg",
  WAIT:  "text-verdict-wait bg-verdict-wait-bg",
  NO:    "text-verdict-no bg-verdict-no-bg",
} as const;

export function VerdictBadge({ verdict }: { verdict: string | null }) {
  const n = normVerdict(verdict) ?? "NO";   // theme.ts:37-42, unchanged
  return (
    <span className={`rounded-[5px] px-[7px] py-[2px] text-micro font-bold
                      tracking-badge ${VERDICT_CLASSES[n]}`}>
      {verdict}
    </span>
  );
}
```

**Sector cell (Pattern B)** — one variable set at runtime; every utility that consumes it is
static. The variable also *inherits*, so setting it once on a table row styles every descendant.

```tsx
<tr style={cssVars({ "--sector": sectorColor(row.sector) })}>   {/* theme.ts:111-113 */}
  <td>
    <span className="inline-block size-[9px] rounded-full bg-(--sector)" />
    <span className="font-mono text-(--sector)">{sectorAbbrOf(row.sector)}</span>
  </td>
</tr>
```

The strings `bg-(--sector)` and `text-(--sector)` are literal in the source, so Tailwind emits them;
only the variable's *value* is runtime, and CSS variables are resolved by the browser, not the
build. That is the seam that reconciles runtime colour with a static build — and it preserves
`sectorColor`'s `?? colors.textFaint` fallback for free, which Pattern A cannot.

**Bar (Pattern B for colour + inline width)** — replaces `bar()` (`theme.ts:119-124`):

```tsx
export function Bar({ color, widthPct }: { color: string; widthPct: number }) {
  return (
    <span className="block h-full w-full rounded-[3px] bg-track">
      <span
        className="block h-full rounded-[3px] bg-(--bar)"
        style={cssVars({
          "--bar": color,
          width: `${Math.max(2, Math.min(100, widthPct))}%`,
        })}
      />
    </span>
  );
}
```

Colour goes through a variable (themeable, overridable by a parent); width goes straight to `style`
— there is nothing to gain from indirection on a continuous value.

**The TypeScript helper.** React 18's `CSSProperties` doesn't admit arbitrary `--*` keys, so
Pattern B needs a cast. Contain it once rather than sprinkling `as React.CSSProperties`:

```ts
// frontend/src/theme.ts
export const cssVars = (
  vars: Record<string, string | number>,
): React.CSSProperties => vars as React.CSSProperties;
```

### What each `theme.ts` export becomes

| `theme.ts` export | Becomes |
| --- | --- |
| `colors` (`:6-27`) | `@theme` `--color-*` block |
| `mono`, `sans` (`:3-4`) | `--font-mono`, `--font-sans` |
| `verdictBadgeStyle` (`:44-55`) | static class map (Pattern A) |
| `verdictDotStyle` (`:57-60`) | `inline-block size-[9px] rounded-full bg-(--verdict)` |
| `bar` (`:119-124`) | component, inline width (above) |
| `segItem` (`:126-134`) | conditional class string or `data-active:` variants |
| `tickerStyle` (`:136-141`) | `cursor-pointer border-b-[1.5px] border-dotted border-underline font-bold` |
| `statLabel` (`:143-145`) | `mb-[2px] block text-micro tracking-label text-text-muted` |
| `statMono` (`:146-148`) | `font-mono font-semibold text-(--stat)` + size token or arbitrary value |
| **`verdictColor`, `normVerdict`, `sectorColors`, `sectorAbbr`, `sectorColor`, `sectorAbbrOf`** | **stay as TypeScript** — data and logic, not styling |

The rule that falls out: **Tailwind owns the static vocabulary, TypeScript owns the runtime lookup,
and a CSS custom property is the seam between them.** Everything returning `CSSProperties` for
*static* styling dissolves into classes; everything that is a *map* survives untouched.

---

## 5. Testing (vitest 2.0 + testing-library) and the build pipeline

**Vitest / jsdom.** Vitest reads `frontend/vite.config.ts`, which is built with `defineConfig` from
`vitest/config` (`frontend/vite.config.ts:1`), so `tailwindcss()` in `plugins` is active during
tests as well. That is benign because of Vitest's default CSS handling
(<https://vitest.dev/config/css>): "Configure if CSS should be processed. When excluded, CSS files
will be replaced with empty strings to bypass the subsequent processing." and "By default, Vitest
exports a proxy, bypassing CSS Modules processing. If you rely on CSS properties on your classes,
you have to enable CSS processing using `include` option."

Consequences:

- `import "./index.css"` in a component under test is a no-op stub. No Tailwind compile cost per
  test file, and no need to change `test-setup.ts` (`frontend/src/test-setup.ts` currently only
  imports `@testing-library/jest-dom/vitest`).
- Therefore **no computed styles exist in jsdom**. `toHaveStyle`/`getComputedStyle` assertions
  about Tailwind classes will fail; assert on `toHaveClass` instead. Inline `style` (Pattern B's
  `--sector` variable, and the bar width) *does* survive into the DOM, so `toHaveStyle({ width:
  "42%" })` keeps working — which is a small argument in Pattern B's favour for testability.
- Only enable `test.css.include` if a test genuinely needs computed styles; it makes Tailwind run
  per test file.
- Existing tests (`App.test.tsx`, `Boards.test.tsx`, `CandidateList.test.tsx`,
  `ChartPanel.test.tsx`, `SectorTable.test.tsx`) query by role/text, not class, so adding classes
  should not break them. Watch for tests that assert on exact text nodes if markup is restructured.

**Build pipeline.** `frontend/package.json` runs `tsc -b && vite build`. Tailwind v4 adds nothing
to the TypeScript side — there is no `tailwind.config.ts` to typecheck and no generated types, so
`tsc -b` is untouched. Two TS-adjacent notes:

- **This repo will break on the CSS import as configured.** `frontend/tsconfig.json` sets an
  explicit `"types": ["vitest/globals", "@testing-library/jest-dom"]`, which suppresses automatic
  inclusion of ambient type packages — `vite/client` (which declares `*.css` modules) is not
  there. `import "./index.css"` in `main.tsx` will fail `tsc -b` with "cannot find module". Fix:
  add `"vite/client"` to that `types` array. Same applies to the `@fontsource/*/400.css` imports
  if they are done from JS rather than from the CSS file.
- Pattern B's `style={{ "--sector": color }}` is not assignable to `React.CSSProperties` under
  React 18's types. The usual fix is `style={{ "--sector": color } as React.CSSProperties}` or a
  small typed helper; plan for it, since `tsc -b` gates the build.

CSS output goes through Vite's normal asset pipeline (hashed file in `dist/assets`), so the
FastAPI-serves-both production setup mentioned in `frontend/vite.config.ts:7` needs no change
beyond serving the emitted stylesheet, which it already does for the JS bundle.

---

## Sources

- <https://tailwindcss.com/docs/installation/using-vite>
- <https://tailwindcss.com/docs/theme> and <https://tailwindcss.com/docs/theme#theme-variable-namespaces>
- <https://tailwindcss.com/docs/detecting-classes-in-source-files>
- <https://tailwindcss.com/docs/styling-with-utility-classes>
- <https://tailwindcss.com/docs/adding-custom-styles>
- <https://tailwindcss.com/docs/functions-and-directives>
- <https://tailwindcss.com/docs/font-family>
- <https://tailwindcss.com/docs/compatibility>
- <https://tailwindcss.com/docs/upgrade-guide>
- <https://v3.tailwindcss.com/docs/guides/vite> (for the superseded v3 path)
- <https://fontsource.org/docs/getting-started/install>
- <https://vitest.dev/config/css>
- npm registry manifests: `tailwindcss`, `@tailwindcss/vite`, `@fontsource/space-grotesk`, `@fontsource/ibm-plex-mono`
- `/Users/ajitimur/Projects/q-scanner-v2/web/src/theme.ts`, `web/index.html`, `web/src/App.tsx`, `web/src/main.tsx`, `web/package.json`
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`,
  `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test-setup.ts` (this repo)
