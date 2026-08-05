import { useEffect, useState } from "react";
import { fetchBoards, type Board, type BoardRow, type BoardsResponse } from "./api/client";

/**
 * Screen 2 — the five leaderboards per market (spec §5.2). A peer tab off the
 * nightly path: everything that matters is already a candidate, so this is the
 * "who moved most" board, ranked on **pure return, no volatility adjustment**
 * (ticket 06 R9). Each row carries the `k/5` breadth badge, a `NEW` marker, and —
 * on the 1w board only — the ≥30%/5d surge flag. No smoothing anywhere.
 */

// Sub-4% ADR is what the one toggle hides (ticket 06 R8). A percentage of price.
const LOW_ADR = 0.04;

const LOOKBACK_TITLES: Record<string, string> = {
  "1w": "1 week",
  "1m": "1 month",
  "3m": "3 months",
  "6m": "6 months",
  "12m": "12 months",
};

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

export default function Boards({ market }: { market: string }) {
  const [boards, setBoards] = useState<BoardsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The one ADR toggle, identical on both surfaces, defaults **off** — nothing
  // is ever hidden unless the user hides it (ticket 06 R8).
  const [hideLowAdr, setHideLowAdr] = useState(false);

  useEffect(() => {
    let live = true;
    setBoards(null);
    setError(null);
    fetchBoards(market)
      .then((b) => live && setBoards(b))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [market]);

  if (error) return <p role="alert">Could not reach the backend: {error}</p>;
  if (!boards) return <p>Loading {market} boards…</p>;
  if (boards.session === null) {
    return (
      <section aria-label={`${market} boards`}>
        <p className="empty-state">No run yet for {market}. Nothing to show tonight.</p>
      </section>
    );
  }

  return (
    <section aria-label={`${market} boards`}>
      <label className="adr-toggle">
        <input
          type="checkbox"
          checked={hideLowAdr}
          onChange={(e) => setHideLowAdr(e.target.checked)}
        />
        Hide sub-4% ADR names
      </label>
      <div className="boards">
        {boards.boards.map((board) => (
          <BoardTable key={board.lookback} board={board} hideLowAdr={hideLowAdr} />
        ))}
      </div>
    </section>
  );
}

function BoardTable({ board, hideLowAdr }: { board: Board; hideLowAdr: boolean }) {
  const title = LOOKBACK_TITLES[board.lookback] ?? board.lookback;
  // The toggle hides sub-4% ADR names *before the eye*, but never filters a name
  // whose ADR could not be computed (null) — that is not evidence of low vol.
  const rows = hideLowAdr
    ? board.rows.filter((r) => r.adr === null || r.adr >= LOW_ADR)
    : board.rows;

  return (
    <table aria-label={`${board.lookback} board — top 30 by return over ${title}`}>
      <caption>
        {board.lookback} · top 30 by return over {title}
      </caption>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Ticker</th>
          <th scope="col">Return</th>
          <th scope="col">k/5</th>
          <th scope="col">ADR</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <BoardRowView key={r.symbol} row={r} rank={i + 1} />
        ))}
      </tbody>
    </table>
  );
}

function BoardRowView({ row, rank }: { row: BoardRow; rank: number }) {
  return (
    <tr>
      <td>{rank}</td>
      <td>
        {row.symbol}
        {row.is_new && (
          <span className="badge badge-new" title="Absent from this board last session">
            {" "}
            NEW
          </span>
        )}
        {row.surge && (
          <span className="badge badge-surge" title="Up ≥30% over the five-day window">
            {" "}
            ↑30%/5d
          </span>
        )}
      </td>
      <td>{pct(row.raw_return)}</td>
      <td title="Lookbacks currently led — a persistence count, not a quality score">
        {row.breadth}/5
      </td>
      <td>{row.adr === null ? "—" : pct(row.adr)}</td>
    </tr>
  );
}
