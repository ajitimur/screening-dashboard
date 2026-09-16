// PROTOTYPE — throwaway. The floating variant switcher (dev builds only).
//
// The variant key lives in `?variant=` so a view is shareable and reload-stable.
// The shell's router canonicalises the query on every navigation; a marked
// prototype line in App.tsx `toLocation` carries `variant` across. Switching
// here uses `replaceState` (no shell re-render needed: the variant is local
// state seeded from the bar).

import { useEffect, useState } from "react";
import "./prototype.css";

export const VARIANTS = [
  { key: "current", name: "Current two bands" },
  { key: "A", name: "Briefing lanes" },
  { key: "B", name: "Annotated ledger" },
  { key: "C", name: "Rotation map" },
] as const;
export type VariantKey = (typeof VARIANTS)[number]["key"];

export const PROTOTYPE_ENABLED = import.meta.env.DEV;

function readVariant(): VariantKey {
  const raw = new URLSearchParams(window.location.search).get("variant");
  return (VARIANTS.some((v) => v.key === raw) ? raw : "current") as VariantKey;
}

function writeVariant(key: VariantKey) {
  const url = new URL(window.location.href);
  url.searchParams.set("variant", key);
  window.history.replaceState(null, "", `${url.pathname}?${url.searchParams}`);
}

export function useVariant(): [VariantKey, (k: VariantKey) => void] {
  const [variant, setVariant] = useState<VariantKey>(() =>
    PROTOTYPE_ENABLED ? readVariant() : "current",
  );
  const set = (k: VariantKey) => {
    writeVariant(k);
    setVariant(k);
  };
  return [variant, set];
}

export function PrototypeSwitcher({
  current,
  onChange,
}: {
  current: VariantKey;
  onChange: (k: VariantKey) => void;
}) {
  const idx = VARIANTS.findIndex((v) => v.key === current);
  const step = (d: number) =>
    onChange(VARIANTS[(idx + d + VARIANTS.length) % VARIANTS.length].key);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable)
      )
        return;
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!PROTOTYPE_ENABLED) return null;
  return (
    <div className="proto-switcher" role="group" aria-label="Prototype variant">
      <button type="button" onClick={() => step(-1)} aria-label="Previous variant">
        ←
      </button>
      <span>
        <b>{current}</b> — {VARIANTS[idx].name}
      </span>
      <button type="button" onClick={() => step(1)} aria-label="Next variant">
        →
      </button>
    </div>
  );
}
