"""Build the blind-grading calibration deck.

You grade each chart 1-5 with the score hidden. Then reveal: computed score, the eight dimensions,
and what price actually did over the next 30 sessions.
"""

import os
import json
import numpy as np
import pandas as pd

import chart
from score import score, DIMS, T
import ranks as R

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.environ.get("DECK_OUT", os.path.join(HERE, "deck.html"))

# ---------------------------------------------------------------- assemble the set

us_frames = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
idx_frames = pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl"))
scored = pd.read_pickle(os.path.join(CACHE, "scored_us.pkl"))
idx_scored = pd.read_pickle(os.path.join(CACHE, "scored_idx.pkl"))
sp = os.path.join(CACHE, "sectors_us.pkl")
sectors = pd.read_pickle(sp) if os.path.exists(sp) else {}
rk, elig, C = R.load_or_build()


def clean(d):
    return d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


US = {s: clean(d) for s, d in us_frames.items()}
IDX = {s: clean(d) for s, d in idx_frames.items()}

scored["risk_pct"] = (scored.trigger - scored.base_low) / scored.trigger
gated = scored[(scored.prior_move >= 0.90) & (scored.risk_pct >= 0.005)].copy()

rng = np.random.default_rng(11)
picks = []


def add(sym, row, market, tag, frames):
    picks.append({"symbol": sym, "row": row, "market": market, "tag": tag, "frames": frames})


# 1. §3.2's worked examples — best-scoring detection in the relevant era for each
for sym, lo, hi in [("ZM", "2020-01-01", "2020-12-31"), ("AR", "2021-01-01", "2022-12-31"),
                    ("APPS", "2020-01-01", "2021-06-30")]:
    g = scored[(scored.symbol == sym) & (scored.date >= lo) & (scored.date <= hi)]
    g = g[g.risk_pct >= 0.005]
    if len(g):
        add(sym, g.sort_values("stars_bool", ascending=False).iloc[0], "US", "§3.2 worked example", US)

# 2. stratified across the boolean star bands, one name per band-pick to avoid clustering
bands = [(0, 1.5, "1★ band"), (1.5, 2.5, "2★ band"), (2.5, 3.5, "3★ band"),
         (3.5, 4.5, "4★ band"), (4.5, 5.1, "5★ band")]
for lo, hi, lab in bands:
    g = gated[(gated.stars_bool >= lo) & (gated.stars_bool < hi)]
    if not len(g):
        continue
    seen = set()
    take = []
    for _, r in g.sample(frac=1.0, random_state=3).iterrows():
        if r.symbol in seen:
            continue
        seen.add(r.symbol)
        take.append(r)
        if len(take) == 3:
            break
    for r in take:
        add(r.symbol, r, "US", lab, US)

# 3. deliberate junk: passes the detector but should read as unsatisfying
junk = scored[(scored.risk_pct >= 0.005)]
lowadr = junk[junk.adr < 0.025].sample(2, random_state=5)
barcode = junk[junk.orderliness > junk.orderliness.quantile(0.97)].sample(2, random_state=5)
for _, r in pd.concat([lowadr, barcode]).iterrows():
    add(r.symbol, r, "US", "deliberate junk", US)

# 4. IDX — including the partial-lock case D13 is about
idx_scored["orderliness"] = idx_scored.churn / idx_scored.L_longest
part = idx_scored[(idx_scored.zero_rng_in_base > 0.02) & (idx_scored.zero_rng_in_base < 0.30)
                  & (idx_scored.stars >= 4)]
for _, r in part.sample(min(3, len(part)), random_state=4).iterrows():
    add(r.symbol, r, "IDX", "IDX · partial limit-lock (D13)", IDX)
clean_idx = idx_scored[(idx_scored.zero_rng_in_base == 0) & (idx_scored.stars >= 4)]
for _, r in clean_idx.sample(2, random_state=4).iterrows():
    add(r.symbol, r, "IDX", "IDX · clean base", IDX)

# ---------------------------------------------------------------- render

cards = []
rng.shuffle(picks)  # so band ordering carries no hint
for i, p in enumerate(picks):
    sym, r, frames = p["symbol"], p["row"], p["frames"]
    d = frames[sym]
    end = int(r["end"])
    sig = r.to_dict()
    sig["detected"] = True
    if p["market"] == "US":
        pm = r.get("prior_move")
        ss = r.get("sector_share")
        if ss is None or (isinstance(ss, float) and np.isnan(ss)):
            ss = R.sector_share_loo(rk, sectors, sym, r["date"]) if sectors else None
    else:
        pm = ss = None
    sb = score(sig, prior_move=pm, sector_share=ss, mode="boolean")
    sc = score(sig, prior_move=pm, sector_share=ss, mode="continuous")

    # outcome
    hi = d["High"].to_numpy(float)
    lo_ = d["Low"].to_numpy(float)
    cl = d["Close"].to_numpy(float)
    trig, stop = float(r["trigger"]), float(r["base_low"])
    risk = trig - stop
    ent = next((j for j in range(end + 1, min(end + 11, len(d))) if hi[j] >= trig), None)
    if ent is None:
        outcome = "never triggered within 10 sessions"
    else:
        hitj = next((j for j in range(ent, min(ent + 30, len(d))) if lo_[j] <= stop), None)
        if hitj is not None:
            outcome = f"triggered, then stopped out at the base low after {hitj-ent} sessions (−1.0R)"
        else:
            j = min(ent + 30, len(d)) - 1
            outcome = f"triggered, +{(cl[j]-trig)/risk:.1f}R after {j-ent} sessions"

    blind = chart.svg(d, end, sig, lookback=110, forward=0)
    after = chart.svg(d, end, sig, lookback=110, forward=30)

    dim_rows = []
    for name, w in DIMS:
        pt = sb["points"][name]
        ct = sc["points"][name]
        raw = sb["raw"][name]
        rawtxt = "—" if raw is None or (isinstance(raw, float) and np.isnan(raw)) else f"{raw:.3f}"
        bcell = '<td class="na">n/a</td>' if pt is None else f'<td class="{"hit" if pt else "miss"}">{int(pt)}</td>'
        ccell = '<td class="na">n/a</td>' if ct is None else f'<td class="cont">{ct:.2f}</td>'
        dim_rows.append(f"<tr><td>{name.replace('_',' ')}</td><td>×{w}</td><td class='raw'>{rawtxt}</td>{bcell}{ccell}</tr>")

    cards.append(
        {
            "i": i + 1,
            "sym": sym,
            "market": p["market"],
            "tag": p["tag"],
            "date": str(pd.to_datetime(r["date"]).date()),
            "blind": blind,
            "after": after,
            "stars_bool": sb["stars"],
            "stars_cont": sc["stars"],
            "dims": "".join(dim_rows),
            "outcome": outcome,
            "meta": f"L={int(r['L'])} · longest valid={int(r['L_longest'])} · windows={int(r['n_windows'])} · "
                    f"ADR={r['adr']*100:.1f}% · stop={r['stop_width_adr']:.2f}×ADR · trigger set by {r['trigger_bound_by']}",
        }
    )

CSS = """
:root{--bg:#0f1115;--fg:#e6e8ee;--mut:#8b93a7;--line:#252a35;--card:#161a22;--acc:#7aa2f7;
--up:#3fb950;--dn:#f85149;--trg:#e3b341;--stp:#f85149;--ok:#3fb950;--no:#5b6270;}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#14161c;--mut:#5b6270;--line:#dfe3ea;
--card:#fff;--up:#1a7f37;--dn:#cf222e;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:28px 24px 8px;max-width:1000px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}.sub{color:var(--mut);max-width:70ch}
main{max-width:1000px;margin:0 auto;padding:16px 24px 80px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:20px 0;overflow:hidden}
.hd{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
.n{font-weight:600}.tag{color:var(--mut);font-size:12px}
.chart{display:block}
svg .bg{fill:transparent}
svg .grid{stroke:var(--line);stroke-width:1}
svg .axis,svg .lbl{fill:var(--mut);font-size:10px}
svg .title{fill:var(--fg);font-size:12px;font-weight:600}
svg .wick,svg .body{stroke-width:1}
svg .up{stroke:var(--up);fill:var(--up)}svg .dn{stroke:var(--dn);fill:var(--dn)}
svg .fut{opacity:.45}
svg .ma10{fill:none;stroke:#7aa2f7;stroke-width:1.2}
svg .ma20{fill:none;stroke:#bb9af7;stroke-width:1.4}
svg .ma50{fill:none;stroke:#8b93a7;stroke-width:1.2;stroke-dasharray:4 3}
svg .ema65{fill:none;stroke:#e0af68;stroke-width:1;stroke-dasharray:2 4}
svg .tri{stroke:var(--acc);stroke-width:1.3;stroke-dasharray:5 3;fill:none}
svg .trigger{stroke:var(--trg);stroke-width:1.4}
svg .stop{stroke:var(--stp);stroke-width:1.2;stroke-dasharray:3 3}
svg .baseband{fill:#7aa2f7;opacity:.06}svg .primaryband{fill:#7aa2f7;opacity:.10}
svg .nowline{stroke:var(--mut);stroke-width:1;stroke-dasharray:2 3}
svg .now{fill:var(--mut)}
.grade{display:flex;gap:8px;align-items:center;padding:12px 16px;border-top:1px solid var(--line);flex-wrap:wrap}
.grade span{color:var(--mut);margin-right:4px}
button{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:6px 12px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
button.sel{background:var(--acc);border-color:var(--acc);color:#0f1115}
.rev{margin-left:auto;border-color:var(--acc);color:var(--acc)}
.reveal{display:none;padding:0 16px 16px;border-top:1px solid var(--line)}
.reveal.on{display:block}
.scores{display:flex;gap:24px;margin:14px 0 8px;flex-wrap:wrap}
.big{font-size:26px;font-weight:700}
.lab{color:var(--mut);font-size:12px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
td.raw{color:var(--mut);font-variant-numeric:tabular-nums}
td.hit{color:var(--ok);font-weight:600}td.miss{color:var(--no)}td.na{color:var(--mut);font-style:italic}
td.cont{color:var(--acc);font-variant-numeric:tabular-nums}
.outcome{padding:10px 12px;background:rgba(122,162,247,.08);border-radius:6px;margin:10px 0}
.meta{color:var(--mut);font-size:12px;margin:6px 0}
.legend{color:var(--mut);font-size:12px;padding:8px 24px;max-width:1000px;margin:0 auto}
.legend b{color:var(--fg);font-weight:600}
#summary{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
padding:10px 24px;font-size:13px;display:flex;gap:16px;align-items:center}
#summary code{color:var(--acc);word-break:break-all}
"""

JS = """
const grades={};
document.querySelectorAll('.g').forEach(b=>b.onclick=()=>{
  const id=b.dataset.id;grades[id]=b.dataset.v;
  document.querySelectorAll(`.g[data-id="${id}"]`).forEach(x=>x.classList.remove('sel'));
  b.classList.add('sel');upd();});
document.querySelectorAll('.rev').forEach(b=>b.onclick=()=>{
  document.getElementById('r'+b.dataset.id).classList.toggle('on');});
function upd(){
  const ks=Object.keys(grades).sort((a,b)=>a-b);
  document.getElementById('out').textContent=ks.map(k=>k+':'+grades[k]).join(' ')||'(none yet)';
  document.getElementById('cnt').textContent=ks.length;
}
"""

html = [f"<style>{CSS}</style>", "<header><h1>Star score calibration — blind grading deck</h1>",
        "<p class='sub'>Grade each chart 1–5 the way you would on stream, <b>before</b> revealing. "
        "The score, its eight dimensions and what price actually did next are all hidden until you click reveal. "
        "Where you and the score disagree is the output of this ticket.</p></header>",
        "<div class='legend'><b>On the chart:</b> blue bands = the retained valid windows (darker = the primary, "
        "shortest window) · dashed blue = §3.2's fitted triangle · gold = trigger · red dashes = estimated stop "
        "(base low) · MAs: <span style='color:#7aa2f7'>10</span> "
        "<span style='color:#bb9af7'>20</span> <span style='color:#8b93a7'>50</span> "
        "<span style='color:#e0af68'>65 EMA</span>.</div>", "<main>"]

for c in cards:
    html.append(f"""
<div class="card">
  <div class="hd"><div class="n">#{c['i']} · {c['sym']} <span class="tag">· {c['market']} · {c['date']}</span></div>
    <div class="tag">grade before revealing</div></div>
  {c['blind']}
  <div class="grade"><span>your grade</span>
    {''.join(f'<button class="g" data-id="{c["i"]}" data-v="{v}">{v}★</button>' for v in range(1,6))}
    <button class="rev" data-id="{c['i']}">reveal</button></div>
  <div class="reveal" id="r{c['i']}">
    <div class="scores">
      <div><div class="big">{c['stars_bool']:.2f}★</div><div class="lab">boolean rubric (§3.5 literal)</div></div>
      <div><div class="big">{c['stars_cont']:.2f}★</div><div class="lab">continuous variant</div></div>
    </div>
    <div class="meta">{c['meta']} · <b>{c['tag']}</b></div>
    <table><tr><th>dimension</th><th>w</th><th>raw</th><th>bool</th><th>cont</th></tr>{c['dims']}</table>
    <div class="outcome"><b>What happened next:</b> {c['outcome']}</div>
    {c['after']}
  </div>
</div>""")

html.append("</main>")
html.append("<div id='summary'><span>graded <b id='cnt'>0</b>/%d — paste this back to Claude:</span>"
            "<code id='out'>(none yet)</code></div>" % len(cards))
html.append(f"<script>{JS}</script>")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    f.write("".join(html))
print(f"wrote {OUT} with {len(cards)} cards")
print(pd.DataFrame([{"i": c["i"], "sym": c["sym"], "mkt": c["market"], "tag": c["tag"],
                     "bool": round(c["stars_bool"], 2), "cont": round(c["stars_cont"], 2)}
                    for c in cards]).to_string(index=False))
