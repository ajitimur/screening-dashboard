"""Render the ticket-16 line deck: which upper boundary sits where the eye would draw it?

The measurement in compare.py is one-sided on the trigger but it cannot answer this — it says the
OLS line is too low, not that the envelope is right. So the deck asks the eye directly, blind:
each card draws both fitted lines as A and B, with the A/B assignment randomised per card, and the
answer is A / B / neither. Nothing on the card says which is which.

Stratified so the answer is not dominated by the cases where the two fits nearly coincide (seed 16):

  near   20 cards  the fits agree to within 0.1 ADR at the trigger — the typical detection
  far    15 cards  top quartile of disagreement — where the choice actually bites
  cut    15 cards  setups the envelope would newly reject on D6's 1xADR gate, which is the
                   29.7% of the pool adopting it costs; the eye should say whether losing them hurts

Run: compare.py -> build_deck16.py -> (grade) -> analyse_deck.py grades16.txt
"""

import os
import sys
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

import chart16  # noqa: E402

SEED = 16
STRATA = {"near": 20, "far": 15, "cut": 15}


def clean(d):
    return d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


CSS = """
:root{--bg:#0f1115;--fg:#e6e8ee;--mut:#8b93a7;--line:#252a35;--card:#161a22;--acc:#7aa2f7;
--up:#3fb950;--dn:#f85149;--stp:#f85149;--fa:#e3b341;--fb:#bb9af7;}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#14161c;--mut:#5b6270;--line:#dfe3ea;
--card:#fff;--up:#1a7f37;--dn:#cf222e;--fa:#9a6700;--fb:#8250df;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:64px}
header{padding:28px 24px 8px;max-width:1000px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}.sub{color:var(--mut);max-width:75ch}
.keys{color:var(--mut);font-size:12px;margin-top:10px}
.keys kbd{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 6px;
font:12px ui-monospace,monospace;color:var(--fg)}
main{max-width:1000px;margin:0 auto;padding:16px 24px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:20px 0;
overflow:hidden;scroll-margin-top:12px}
.card.here{border-color:var(--acc)}.card.done .hd{opacity:.75}
.hd{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;
border-bottom:1px solid var(--line)}
.n{font-weight:600}.tag{color:var(--mut);font-size:12px}
svg .bg{fill:transparent}svg .grid{stroke:var(--line);stroke-width:1}
svg .axis,svg .lbl{fill:var(--mut);font-size:10px}
svg .title{fill:var(--fg);font-size:12px;font-weight:600}
svg .wick,svg .body{stroke-width:1}
svg .up{stroke:var(--up);fill:var(--up)}svg .dn{stroke:var(--dn);fill:var(--dn)}
svg .ma10{fill:none;stroke:#7aa2f7;stroke-width:1.2}
svg .ma20{fill:none;stroke:#bb9af7;stroke-width:1.4}
svg .ma50{fill:none;stroke:#8b93a7;stroke-width:1.2;stroke-dasharray:4 3}
svg .ema65{fill:none;stroke:#e0af68;stroke-width:1;stroke-dasharray:2 4}
svg .fit{stroke-width:1.6;fill:none}
svg .fitA{stroke:var(--fa)}svg .fitB{stroke:var(--fb)}
svg .fitlblA{fill:var(--fa);font-size:12px;font-weight:700}
svg .fitlblB{fill:var(--fb);font-size:12px;font-weight:700}
svg .stop{stroke:var(--stp);stroke-width:1.2;stroke-dasharray:3 3}
svg .primaryband{fill:#7aa2f7;opacity:.10}
.grade{display:flex;gap:8px;align-items:center;padding:12px 16px;border-top:1px solid var(--line);
flex-wrap:wrap}.grade span{color:var(--mut);margin-right:4px}
button{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:6px 12px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
button.sel{background:var(--acc);border-color:var(--acc);color:#0f1115}
.legend{color:var(--mut);font-size:12px;padding:8px 24px;max-width:1000px;margin:0 auto}
.legend b{color:var(--fg);font-weight:600}
#bar{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
padding:10px 24px;font-size:13px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
#bar b{color:var(--acc)}
#out{width:100%;max-width:100%;height:74px;background:var(--bg);color:var(--fg);
border:1px solid var(--line);border-radius:6px;padding:8px;font:12px ui-monospace,monospace;
display:none}#out.on{display:block}
"""

JS = """
const N=%N%, KEY='wf16deck';
// file:// origins can refuse localStorage; grading must work anyway, so every access is guarded
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){return {};}}
function save(v){try{localStorage.setItem(KEY,JSON.stringify(v));}catch(e){}}
let G=load(), cur=0;
function paint(){
  for(let i=0;i<N;i++){
    const c=document.getElementById('c'+i);
    c.classList.toggle('here',i===cur);
    c.classList.toggle('done',G[i]!==undefined);
    c.querySelectorAll('button[data-v]').forEach(b=>
      b.classList.toggle('sel',G[i]===b.dataset.v));
  }
  document.getElementById('cnt').textContent=Object.keys(G).length+' / '+N;
}
function set(i,v){ if(G[i]===v) delete G[i]; else G[i]=v; save(G); paint();
  if(G[i]!==undefined&&i<N-1){cur=i+1;document.getElementById('c'+cur).scrollIntoView({block:'center',behavior:'smooth'});}
  paint();
}
document.addEventListener('keydown',e=>{
  const k=e.key.toLowerCase();
  if(k==='a'||k==='b'||k==='n'){set(cur,k);e.preventDefault();}
  else if(k==='j'&&cur<N-1){cur++;document.getElementById('c'+cur).scrollIntoView({block:'center'});paint();}
  else if(k==='k'&&cur>0){cur--;document.getElementById('c'+cur).scrollIntoView({block:'center'});paint();}
});
function exp(){
  const o=document.getElementById('out');
  o.classList.add('on');
  o.value=Array.from({length:N},(_,i)=>G[i]||'-').join('');
  o.select();
}
"""


def build():
    df = pd.read_pickle(os.path.join(CACHE, "fit_compare.pkl"))
    df = df.reset_index(drop=True)
    a = df.adr * df.close
    # the eye question is about the LINE, so the strata are drawn on the line-only difference
    # (env vs OLS under 08's own min() clamp), not on the clamp, which is a separate fork
    df["dtrig"] = (df.trig_env_min - df.trig_ols_min) / a
    df["cut"] = df.stopw_env_min > df.adr

    rng = np.random.default_rng(SEED)
    far_cut = df.dtrig.quantile(0.75)
    pools = {
        "near": df[(df.dtrig.abs() < 0.10) & (~df.cut)],
        "far": df[(df.dtrig >= far_cut) & (~df.cut)],
        "cut": df[df.cut],
    }
    picks = []
    for name, k in STRATA.items():
        p = pools[name]
        take = rng.choice(len(p), size=min(k, len(p)), replace=False)
        for t in take:
            r = p.iloc[int(t)].to_dict()
            r["stratum"] = name
            picks.append(r)
    rng.shuffle(picks)

    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}

    cards, meta = [], []
    for i, r in enumerate(picks):
        frames = us if r["market"] == "US" else idx
        d = frames.get(r["symbol"])
        if d is None:
            continue
        which = ["ols", "env"]
        if rng.random() < 0.5:
            which = which[::-1]
        assign = {"A": which[0], "B": which[1]}
        s = chart16.svg(d, int(r["end"]), int(r["L"]), float(r["adr"]), float(r["close"]),
                        assign, title=f'{r["symbol"]}  {pd.to_datetime(r["date"]).date()}')
        n = len(cards)
        cards.append(
            f'<div class="card" id="c{n}"><div class="hd"><span class="n">#{n+1}</span>'
            f'<span class="tag">base {int(r["L"])} bars &middot; ADR {r["adr"]*100:.1f}%</span></div>'
            f'{s}<div class="grade"><span>which line sits where you would draw it?</span>'
            f'<button data-v="a" onclick="set({n},\'a\')">A</button>'
            f'<button data-v="b" onclick="set({n},\'b\')">B</button>'
            f'<button data-v="n" onclick="set({n},\'n\')">neither</button></div></div>'
        )
        meta.append({"card": n, "symbol": r["symbol"], "market": r["market"],
                     "date": str(pd.to_datetime(r["date"]).date()), "end": int(r["end"]),
                     "L": int(r["L"]), "stratum": r["stratum"], "dtrig": float(r["dtrig"]),
                     "cut": bool(r["cut"]), "A": assign["A"], "B": assign["B"]})

    pd.DataFrame(meta).to_csv(os.path.join(HERE, "deck16_manifest.csv"), index=False)
    with open(os.path.join(HERE, "deck16_key.json"), "w") as f:
        json.dump(meta, f, indent=1)

    html = [
        f"<style>{CSS}</style>",
        '<header><h1>Ticket 16 — where should the upper line sit?</h1>',
        '<p class="sub">Every card is a detected setup, drawn over <b>the primary window only</b>. '
        'Two candidate upper boundaries are drawn on each: <b>A</b> and <b>B</b>. They are the same '
        'two fitting methods on every card, but <b>which one is A is randomised per card</b>, so you '
        'cannot follow a colour. Pick the line that sits where you would have drawn it — the line you '
        'would hang a price alert on. <b>neither</b> is a real answer and worth using.</p>'
        '<p class="sub">Candles piercing the line is fine and expected (§3.2). The dashed red level is '
        'the stop (the base low); it is the same under both.</p>'
        f'<p class="keys"><kbd>a</kbd> <kbd>b</kbd> <kbd>n</kbd> answer and advance &middot; '
        f'<kbd>j</kbd>/<kbd>k</kbd> move</p></header>',
        "<main>", *cards, "</main>",
        '<div id="bar"><span>answered <b id="cnt">0</b></span>'
        '<button onclick="exp()">export</button>'
        '<textarea id="out" readonly></textarea></div>',
        f"<script>{JS.replace('%N%', str(len(cards)))}</script>",
    ]
    out = os.path.join(HERE, "deck16.html")
    with open(out, "w") as f:
        f.write("".join(html))
    print(f"wrote {out}  ({len(cards)} cards)")
    print(pd.DataFrame(meta).stratum.value_counts().to_string())


if __name__ == "__main__":
    build()
