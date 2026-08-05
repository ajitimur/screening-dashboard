"""Render the round-2 grading decks.

Two deliberate differences from ticket 09's deck, both methodological:

  1. NOTHING IS REVEALED DURING GRADING. Round 1 let you reveal the score card by card, which is
     fine over 27 charts and not fine over 276: seeing the machine's answer teaches you what it
     rewards, and later grades stop being independent of it. The reveal button only appears after
     the deck is submitted.
  2. Deck D draws BARE CANDLES for every card — rejects and detections alike — because the overlays
     would announce which is which. Its question is different, and printed on the deck.

Grading is keyboard-first (1–5 grades and advances, 0 clears, j/k move) and survives a reload via
localStorage, because 276 cards is more than one sitting.
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
OUTDIR = os.path.join(HERE, "decks")

import chart  # noqa: E402

DECK_BLURB = {
    "A": ("Deck A — core calibration (120 cards)",
          "Grade each chart 1–5 the way you would on stream. These are detected setups with the "
          "detector's evidence drawn on. Nothing is revealed until you submit the whole deck — "
          "that is deliberate, so a card you grade late is not influenced by a score you saw early."),
    "B": ("Deck B — trigger probe (52 cards)",
          "Same instruction: grade 1–5. This deck is split on something specific about the trigger, "
          "and you are not told what, because the point is whether your eye separates the two halves "
          "without being told."),
    "C": ("Deck C — IDX probe (52 cards)",
          "IDX names only. Grade 1–5. Again split on something specific and again not told what."),
    "D": ("Deck D — is there a setup here at all? (40 cards)",
          "DIFFERENT QUESTION. No overlays on these charts — no base, no trigger, no fitted lines. "
          "Grade 1–5 for: <b>is there a tradeable breakout/continuation setup on this chart, as of "
          "the last bar shown?</b> 1 = nothing here, 5 = I would put this on the watchlist tonight. "
          "Some of these are charts the detector threw away."),
}


def build():
    picks = pd.read_pickle(os.path.join(CACHE, "picks_r2.pkl"))
    us = {s: d for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    idxf = {s: d for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}

    def clean(d):
        return d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)

    US = {s: clean(d) for s, d in us.items()}
    IDX = {s: clean(d) for s, d in idxf.items()}

    rng = np.random.default_rng(151)
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = []

    by_deck = {}
    for k, p in enumerate(picks):
        by_deck.setdefault(p["deck"], []).append((k, p))

    for deck, items in sorted(by_deck.items()):
        order = rng.permutation(len(items))
        cards = []
        for pos, oi in enumerate(order):
            k, p = items[int(oi)]
            r = p["row"]
            sym = p["symbol"]
            frames = US if p["market"] == "US" else IDX
            d = frames[sym]
            end = int(r["end"])
            sig = None
            if deck != "D" and not pd.isna(r.get("L", np.nan)):
                sig = dict(r)
                sig["detected"] = True
            svg = chart.svg(d, end, sig, lookback=110, forward=0)
            cid = f"{deck}{pos+1:03d}"
            cards.append({"cid": cid, "pick": k, "sym": sym,
                          "date": str(pd.to_datetime(r["date"]).date()),
                          "market": p["market"], "svg": svg})
            manifest.append({"cid": cid, "deck": deck, "pick": k, "symbol": sym,
                             "date": str(pd.to_datetime(r["date"]).date()),
                             "market": p["market"], "tag": p["tag"],
                             "repeat_of": p["repeat_of"]})
        write_deck(deck, cards)
        print(f"deck {deck}: {len(cards)} cards -> {os.path.join(OUTDIR, f'deck_{deck}.html')}")

    pd.DataFrame(manifest).to_pickle(os.path.join(CACHE, "manifest_r2.pkl"))
    pd.DataFrame(manifest).to_csv(os.path.join(OUTDIR, "manifest.csv"), index=False)
    print(f"manifest: {len(manifest)} cards")


CSS = """
:root{--bg:#0f1115;--fg:#e6e8ee;--mut:#8b93a7;--line:#252a35;--card:#161a22;--acc:#7aa2f7;
--up:#3fb950;--dn:#f85149;--trg:#e3b341;--stp:#f85149;}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#14161c;--mut:#5b6270;--line:#dfe3ea;
--card:#fff;--up:#1a7f37;--dn:#cf222e;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:64px}
header{padding:28px 24px 8px;max-width:1000px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}.sub{color:var(--mut);max-width:75ch}
.keys{color:var(--mut);font-size:12px;margin-top:10px}
.keys kbd{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 6px;
font:12px ui-monospace,monospace;color:var(--fg)}
main{max-width:1000px;margin:0 auto;padding:16px 24px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:20px 0;overflow:hidden;
scroll-margin-top:12px}
.card.here{border-color:var(--acc)}
.card.done .hd{opacity:.75}
.hd{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
.n{font-weight:600}.tag{color:var(--mut);font-size:12px}
svg .bg{fill:transparent}svg .grid{stroke:var(--line);stroke-width:1}
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
svg .nowline{stroke:var(--mut);stroke-width:1;stroke-dasharray:2 3}svg .now{fill:var(--mut)}
.grade{display:flex;gap:8px;align-items:center;padding:12px 16px;border-top:1px solid var(--line);flex-wrap:wrap}
.grade span{color:var(--mut);margin-right:4px}
button{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:6px 12px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
button.sel{background:var(--acc);border-color:var(--acc);color:#0f1115}
.legend{color:var(--mut);font-size:12px;padding:8px 24px;max-width:1000px;margin:0 auto}
.legend b{color:var(--fg);font-weight:600}
#bar{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
padding:10px 24px;font-size:13px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
#bar b{color:var(--acc)}
#out{width:100%;max-width:100%;height:74px;background:var(--bg);color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:8px;font:12px ui-monospace,monospace;display:none}
#out.on{display:block}
"""

JS = """
const DECK=%DECK%, N=%N%;
const KEY='wf15-'+DECK;
let g=JSON.parse(localStorage.getItem(KEY)||'{}');
let cur=0;
const cards=[...document.querySelectorAll('.card')];
function paint(){
  cards.forEach((c,i)=>{
    const id=c.dataset.cid;
    c.classList.toggle('here',i===cur);
    c.classList.toggle('done',!!g[id]);
    c.querySelectorAll('.gb').forEach(b=>b.classList.toggle('sel',g[id]==b.dataset.v));
  });
  const n=Object.keys(g).length;
  document.getElementById('cnt').textContent=n;
  document.getElementById('pct').textContent=Math.round(100*n/N)+'%';
  localStorage.setItem(KEY,JSON.stringify(g));
}
function setg(i,v){
  const id=cards[i].dataset.cid;
  if(v===0){delete g[id];}else{g[id]=String(v);}
  paint();
  if(v!==0&&i<cards.length-1){cur=i+1;cards[cur].scrollIntoView({behavior:'smooth',block:'start'});paint();}
}
cards.forEach((c,i)=>{
  c.querySelectorAll('.gb').forEach(b=>b.onclick=()=>{cur=i;setg(i,+b.dataset.v);});
  c.addEventListener('mouseenter',()=>{cur=i;paint();});
});
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA')return;
  if(e.key>='1'&&e.key<='5'){setg(cur,+e.key);e.preventDefault();}
  else if(e.key==='0'||e.key==='Backspace'){setg(cur,0);e.preventDefault();}
  else if(e.key==='j'){cur=Math.min(cur+1,cards.length-1);cards[cur].scrollIntoView({block:'start'});paint();}
  else if(e.key==='k'){cur=Math.max(cur-1,0);cards[cur].scrollIntoView({block:'start'});paint();}
});
document.getElementById('exp').onclick=()=>{
  const t=document.getElementById('out');
  t.classList.add('on');
  t.value=DECK+' '+cards.map(c=>c.dataset.cid+':'+(g[c.dataset.cid]||'-')).join(' ');
  t.select();
};
document.getElementById('clr').onclick=()=>{if(confirm('Clear all grades in this deck?')){g={};paint();}};
paint();
"""


def write_deck(deck, cards):
    title, blurb = DECK_BLURB[deck]
    legend = ("<div class='legend'><b>On the chart:</b> blue bands = the retained valid windows "
              "(darker = the primary, shortest window) · dashed blue = the fitted triangle · gold = "
              "trigger · red dashes = estimated stop (base low) · MAs: <span style='color:#7aa2f7'>10</span> "
              "<span style='color:#bb9af7'>20</span> <span style='color:#8b93a7'>50</span> "
              "<span style='color:#e0af68'>65 EMA</span>.</div>") if deck != "D" else (
              "<div class='legend'><b>On the chart:</b> candles and MAs only — "
              "<span style='color:#7aa2f7'>10</span> <span style='color:#bb9af7'>20</span> "
              "<span style='color:#8b93a7'>50</span> <span style='color:#e0af68'>65 EMA</span>. "
              "No detector overlays on this deck, by design.</div>")

    html = [f"<style>{CSS}</style>",
            f"<header><h1>{title}</h1><p class='sub'>{blurb}</p>",
            "<p class='keys'><kbd>1</kbd>–<kbd>5</kbd> grade and advance · <kbd>0</kbd> clear · "
            "<kbd>j</kbd>/<kbd>k</kbd> move · progress is saved in this browser, so you can stop "
            "and come back. When you are done, hit <b>export</b> and paste the line back.</p></header>",
            legend, "<main>"]
    for c in cards:
        html.append(f"""
<div class="card" data-cid="{c['cid']}">
  <div class="hd"><div class="n">{c['cid']} · {c['sym']} <span class="tag">· {c['market']} · {c['date']}</span></div>
    <div class="tag">grade 1–5</div></div>
  {c['svg']}
  <div class="grade"><span>your grade</span>
    {''.join(f'<button class="gb" data-v="{v}">{v}★</button>' for v in range(1, 6))}</div>
</div>""")
    html.append("</main>")
    html.append("<div id='bar'><span>graded <b id='cnt'>0</b>/%d (<span id='pct'>0%%</span>)</span>"
                "<button id='exp'>export</button><button id='clr'>clear</button>"
                "<textarea id='out' readonly></textarea></div>" % len(cards))
    html.append("<script>%s</script>" % JS.replace("%DECK%", json.dumps(deck)).replace("%N%", str(len(cards))))
    with open(os.path.join(OUTDIR, f"deck_{deck}.html"), "w") as f:
        f.write("".join(html))


if __name__ == "__main__":
    build()
