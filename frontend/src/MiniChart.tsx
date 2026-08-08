import { useEffect, useRef, useState } from "react";
import { Chart } from "./Chart";
import { loadChart } from "./chartCache";
import type { ChartResponse } from "./api/client";

// The thumbnail window (spec §6.4): 60 bars, the same the sheet reads, so a mini
// already painted makes the sheet's open a cache hit. `bars=` exists precisely so
// a 60-bar thumbnail never ships a full price history.
const MINI_BARS = 60;
// Prefetch a little before the frame scrolls in, so the shape is usually already
// there when the eye arrives (spec §6.4).
const ROOT_MARGIN = "200px";
// A thumbnail is confirmation, not the primary read — short enough to sit under a
// card's numbers without dominating it.
const MINI_HEIGHT = 56;

/**
 * A lazy mini chart (spec §6.4): the at-a-glance shape on a Setups card or a
 * Leaders grid cell — and **nowhere else**. It reads nothing until it scrolls
 * near the viewport (an `IntersectionObserver` with a 200px margin), asks for the
 * 60-bar window, and shares one frontend cache with the sheet and its siblings so
 * a grid of them is not a fetch storm.
 *
 * **It fails silently** (spec §7.7): a failed or slow read is just an empty frame
 * — no message, no notice, no alert. This is the one exemption from the panel-
 * notice rule, granted on volume: at 60 cards, per-instance error text is 60
 * apologies, and the card's own numbers are load-bearing while the chart is only
 * confirmation. The canvas is `aria-hidden` — decorative (spec §8.9).
 *
 * `onActivate` (optional) opens the sheet on click — the mini is a second mouse
 * door to the same sheet the card's ticker <button> opens for the keyboard; it
 * stays out of the tab order (the redundant, decorative surface) so 60 cards do
 * not add 60 tab stops.
 */
export default function MiniChart({
  market,
  symbol,
  onActivate,
}: {
  market: string;
  symbol: string;
  onActivate?: () => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [data, setData] = useState<ChartResponse | null>(null);

  // Lazy trigger: observe the frame; the first time it nears the viewport, mark
  // it visible and stop observing. Keyed on symbol so a swapped cell re-arms.
  useEffect(() => {
    const el = frameRef.current;
    if (el === null) return;
    setVisible(false);
    setData(null);
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: ROOT_MARGIN },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [symbol]);

  // Read once visible. A rejection is swallowed — the frame simply stays empty
  // (spec §7.7); the shared cache has already evicted it so a later open retries.
  useEffect(() => {
    if (!visible) return;
    let live = true;
    loadChart(market, symbol, MINI_BARS)
      .then((d) => live && setData(d))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [visible, market, symbol]);

  return (
    <div
      ref={frameRef}
      className="mini-chart"
      aria-hidden="true"
      onClick={onActivate}
    >
      {data && <Chart data={data} height={MINI_HEIGHT} />}
    </div>
  );
}
