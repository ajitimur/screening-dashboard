"""PROTOTYPE — throwaway. Inlines tightness.json into template.html.

A single double-clickable file is the deliverable, and file:// blocks fetch(),
so the data has to live inside the page. Records are shortened to keep it small.

Run:  backend/.venv/bin/python backend/replay/prototype-tightness/build_html.py
Writes tightness.html next to this file.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "tightness.json").read_text())

compact = [
    {
        "s": t["ticker"],
        "d": t["entry_date"],
        # r[0..4] = trailing 3,4,5,6,7-bar range in ADR at the eval session
        "r": [t["range_adr"][str(k)] for k in range(3, 8)],
        "stop": t["stop_adr"],
        "sl3": t["stop_vs_low3_adr"],
        "eh3": t["entry_vs_high3_adr"],
        "ok": t["price_scale_ok"],
        "rr": t["rr10sma"],
        "g": t["gain10sma_pct"],
        "adr": t["adr_pct"],
    }
    for t in d["trades"]
]
payload = {k: d[k] for k in ("n_trades_total", "n_measured", "skipped", "bar_window")}
payload["trades"] = compact

html = (HERE / "template.html").read_text().replace(
    "__DATA__", json.dumps(payload, separators=(",", ":"))
)
out = HERE / "tightness.html"
out.write_text(html)
print(f"wrote {out}  ({len(html)/1024:.0f} KB, {len(compact)} trades)")
