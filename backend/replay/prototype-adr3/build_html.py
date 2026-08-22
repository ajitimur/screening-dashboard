"""PROTOTYPE — throwaway. Inlines adr3.json into template.html.

A single double-clickable file is the deliverable, and file:// blocks fetch(),
so the data has to live inside the page. Records are shortened to keep it small.

Run:  backend/.venv/bin/python backend/replay/prototype-adr3/build_html.py
Writes adr3.html next to this file.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "adr3.json").read_text())


def row(t, entry):
    r = {
        "sp": t["span3_recent_adr"],       # recent 3-bar span, in ADR20
        "pp": t["span3_prior_adr"],        # prior 3-bar span, in ADR20
        "ar": t["adr3_ratio"],             # recent 3-bar avg daily range / prior 3-bar
        "a2": t["adr3_vs_adr20"],          # recent 3-bar avg daily range / ADR20
        "vr": t["vol3_ratio"],             # recent 3-bar avg volume / prior 3-bar
        "v2": t["vol3_vs_vol20"],          # recent 3-bar avg volume / 20-bar avg
    }
    if entry:
        r |= {"s": t["ticker"], "d": t["entry_date"], "m": t["mfe10sma_pct"],
              "rr": t["rr10sma"], "c": 1 if t["continuation"] else 0}
    return r


payload = {k: d[k] for k in ("n_trades_total", "n_measured", "n_background",
                             "skipped", "bar_window", "params")}
payload["entries"] = [row(t, True) for t in d["trades"]]
payload["background"] = [row(t, False) for t in d["background"]]

html = (HERE / "template.html").read_text().replace(
    "__DATA__", json.dumps(payload, separators=(",", ":"))
)
out = HERE / "adr3.html"
out.write_text(html)
print(f"wrote {out}  ({len(html) / 1024:.0f} KB, "
      f"{len(payload['entries'])} entries + {len(payload['background'])} background)")
