"""Build the private interview site: one self-contained HTML page from the real results.

Run: make site    (after make result and make differ)
Open: report/local/site/index.html     (or: make serve, then http://127.0.0.1:8765)

The page shows numbers derived from Coinbase market data. It is written to report/local/ (gitignored)
and is meant for screen sharing only. Do not deploy or send it (README, Coinbase Market Data Terms).
Refuses synthetic results, and labels any capture shorter than 72 hours as partial.
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "local" / "site" / "index.html"
FULL_HOURS = 72  # their period was three days; anything shorter is labelled partial

FRIENDLY = {
    "State definition": "Count every change, not every 50 ms batch",
    "Depth-5 construction": "Keep only 5 price levels, as they did",
    "Counting rule: time-weighted": "Weight by time",
    "Counting rule: 1 s grid": "Sample once a second",
    "Locked and crossed books": "Keep locked/crossed books",
    "Timestamp field": "Use receive time",
    "Period length": "Use only 72 hours",
}


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def bridge(r: dict, w: dict) -> list[dict]:
    """Four bars from my number to theirs: mine, the largest factor alone, the two largest together, theirs."""
    c = w["combined"]
    pair = c if c["value"] is not None else c.get("fallback")
    steps = [{"label": "My measurement", "value": r["verdict"]["share"], "kind": "mine"}]
    if pair:
        first = next(row for row in w["rows"] if row["factor"] == pair["factors"][0])
        steps.append({"label": FRIENDLY.get(first["factor"], first["factor"]), "value": first["value"], "kind": "step"})
        steps.append({"label": "…and " + FRIENDLY.get(pair["factors"][1], pair["factors"][1]).lower(),
                      "value": pair["value"], "kind": "step"})
    steps.append({"label": "Their published number", "value": w["theirs"], "kind": "theirs"})
    return steps


def render(r: dict, w: dict) -> str:
    if r.get("synthetic"):
        raise ValueError("refusing to build the site from synthetic sample data")
    v = r["verdict"]
    if not v.get("usable", False):
        raise ValueError("the block-1,000 interval has too few blocks; record more data first")
    e = html.escape
    hours = (r["last_ts_ns"] - r["first_ts_ns"]) / 3.6e12
    span = f"{hours / 24:.1f} days" if hours >= 48 else f"{hours:.1f} hours"
    rule_date = _git("log", "--format=%ad", "--date=format:%d %b %Y", "--diff-filter=A", "--", "docs/match-rule.md") or "before recording"
    steps = bridge(r, w)
    left = steps[-2]["value"] - w["theirs"] if len(steps) == 4 else None
    data = json.dumps({"verdict": v, "hours": r["hour_of_day"], "bridge": steps}).replace("</", "<\\/")
    banner = (f'<div class="partial" role="status">Partial data ({e(span)}). Not a result.</div>' if hours < FULL_HOURS else "")
    remaining = ("" if left is None else
                 f"{abs(left) * 100:.1f} points remain: I couldn\u2019t test the unbatched feed (it needs authentication), and their dates aren\u2019t published.")
    return TEMPLATE.format(
        banner=banner, data=data,
        share=f"{100 * v['share']:.1f}%",
        verdict="Matched" if v["theirs_inside"] else "Did not match",
        gap=f"{v['gap_points']:+.1f} points", ci=f"{100 * v['lo']:.1f}–{100 * v['hi']:.1f}%",
        remaining=e(remaining), states=f"{r['counts']['total']:,}", span=e(span), rule_date=e(rule_date))


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Plumb</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,600;12..96,700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#eceeea;--surface:#f8f9f6;--line:#cdd3cb;--ink:#161a18;--muted:#58625c;--mine:#2a6bc2;--theirs:#7a5a00;--step:#8a938e;--warn-bg:#fff4d6;--warn-line:#c9a227;
--ui:"Bricolage Grotesque","Avenir Next","Segoe UI",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f1312;--surface:#161b19;--line:#2f3a35;--ink:#e9eee9;--muted:#9aa8a0;--mine:#5b95e0;--theirs:#b88a24;--step:#6d7772;--warn-bg:#2a2410;--warn-line:#8a6d12;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0f1312;--surface:#161b19;--line:#2f3a35;--ink:#e9eee9;--muted:#9aa8a0;--mine:#5b95e0;--theirs:#b88a24;--step:#6d7772;--warn-bg:#2a2410;--warn-line:#8a6d12;color-scheme:dark}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 var(--ui)}}
h1,h2{{margin:0;letter-spacing:-.02em;line-height:1.1}} h2{{font-size:1.35rem;font-weight:600}}
p{{margin:0}} .muted{{color:var(--muted)}}
.pad{{max-width:960px;margin-inline:auto;padding-inline:16px}}
.top{{display:flex;align-items:center;gap:12px;padding-block:18px}}
.brand{{font-weight:700;font-size:1.15rem}} .tag{{font-size:.78rem;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 10px}}
.btn{{margin-left:auto;font:500 .85rem var(--ui);color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer}}
.btn:focus-visible{{outline:2px solid var(--mine);outline-offset:2px}}
.partial{{background:var(--warn-bg);border:1px solid var(--warn-line);border-radius:8px;padding:8px 14px;font-weight:500;font-size:.92rem}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:clamp(18px,3vw,30px)}}
section{{margin-top:22px}}
.q{{font-size:clamp(1.05rem,2.2vw,1.3rem);color:var(--muted)}}
.answer{{display:flex;align-items:baseline;gap:18px 28px;flex-wrap:wrap;margin-top:6px}}
.big{{font-weight:700;font-size:clamp(3.6rem,10vw,6rem);letter-spacing:-.05em;line-height:1;font-variant-numeric:tabular-nums}}
.vs{{font-size:1.15rem}} .vs b{{font-weight:600}}
.pill{{display:inline-block;font-weight:600;font-size:.95rem;border:1.5px solid var(--ink);border-radius:999px;padding:3px 12px;margin-right:8px}}
.chart{{position:relative;margin-top:14px}} .chart svg{{display:block;width:100%;height:auto;overflow:visible}}
svg text{{font-family:var(--mono);font-size:11px;fill:var(--muted)}} svg .lbl{{font-family:var(--ui);font-size:13px;font-weight:600;fill:var(--ink)}}
svg .val{{font-family:var(--ui);font-size:13px;font-weight:600;fill:var(--ink)}}
.tip{{position:absolute;pointer-events:none;background:var(--ink);color:var(--bg);font-size:.8rem;padding:5px 9px;border-radius:6px;white-space:nowrap;transform:translate(-50%,-120%);display:none}}
.two{{display:grid;grid-template-columns:1.25fr 1fr;gap:22px;margin-top:22px}}
.facts{{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--surface);margin-top:22px}}
.facts div{{padding:16px 20px;border-right:1px solid var(--line)}} .facts div:last-child{{border-right:0}}
.facts b{{display:block;font-size:1.35rem;letter-spacing:-.02em}} .facts span{{color:var(--muted);font-size:.9rem}}
footer{{margin-block:26px 40px;color:var(--muted);font-size:.85rem}}
@media (max-width:760px){{.two,.facts{{grid-template-columns:1fr}} .facts div{{border-right:0;border-bottom:1px solid var(--line)}}}}
</style></head>
<body><main class="pad">
<div class="top"><span class="brand">Plumb</span><span class="tag">Private copy</span><button class="btn" id="theme" type="button">Dark</button></div>
{banner}
<section class="card">
  <p class="q">Is the Coinbase BTC-USD spread one tick 55.6% of the time, as HFT Architecture published?</p>
  <div class="answer"><div class="big">{share}</div>
    <p class="vs"><span class="pill">{verdict}</span><b>{gap}</b> vs their 55.6% <span class="muted">(95% CI {ci})</span></p></div>
  <div class="chart" id="ruler" role="img" aria-label="My interval against their 55.6 percent"></div>
</section>
<div class="two">
  <section class="card" style="margin-top:0"><h2>Why the numbers differ</h2>
    <div class="chart" id="bridge" role="img" aria-label="From my number to theirs, step by step"></div>
    <p class="muted" style="margin-top:10px;font-size:.92rem">{remaining}</p></section>
  <section class="card" style="margin-top:0"><h2>Does the hour matter?</h2>
    <div class="chart" id="hours"><div class="tip" id="tip"></div></div>
    <p class="muted" style="margin-top:10px;font-size:.92rem">Share by UTC hour with 95% band; dashed line: theirs.</p></section>
</div>
<div class="facts">
  <div><b>{rule_date}</b><span>Match rule committed before any data</span></div>
  <div><b>10 / 10</b><span>States hand-checked against an independent rebuild</span></div>
  <div><b>{states}</b><span>Order-book states over {span}</span></div>
</div>
<footer>One venue · my own recording · batched feed · I never saw their data. Built from Coinbase market data: private, not for distribution.</footer>
</main>
<script id="plumb-data" type="application/json">{data}</script>
<script>
(function(){{
const D=JSON.parse(document.getElementById('plumb-data').textContent), THEIRS=0.556, NS='http://www.w3.org/2000/svg';
const el=(t,a,p)=>{{const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);if(p)p.appendChild(n);return n}};
const txt=(p,x,y,s,a={{}})=>{{const t=el('text',Object.assign({{x,y}},a),p);t.textContent=s;return t}};
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const pct=(x,d=1)=>(100*x).toFixed(d)+'%';
const root=document.documentElement, tb=document.getElementById('theme'), mq=matchMedia('(prefers-color-scheme: dark)');
const dark=()=>root.dataset.theme?root.dataset.theme==='dark':mq.matches;
const label=()=>{{tb.textContent=dark()?'Light':'Dark'}};
try{{const s=localStorage.getItem('plumb-theme');if(s)root.dataset.theme=s}}catch(e){{}}
tb.onclick=()=>{{root.dataset.theme=dark()?'light':'dark';try{{localStorage.setItem('plumb-theme',root.dataset.theme)}}catch(e){{}}label();draw()}};
(mq.addEventListener?mq.addEventListener.bind(mq,'change'):mq.addListener.bind(mq))(()=>{{label();draw()}});
function fresh(id,h){{const b=document.getElementById(id);b.querySelectorAll('svg').forEach(s=>s.remove());const w=Math.max(280,b.clientWidth);const s=el('svg',{{viewBox:`0 0 ${{w}} ${{h}}`}});b.insertBefore(s,b.firstChild);return [s,w]}}
function ruler(){{
 const V=D.verdict,[s,w]=fresh('ruler',70),m=14;
 const lo=Math.max(0,Math.floor((Math.min(V.lo,THEIRS)-.05)*10)/10),hi=Math.min(1,Math.ceil((Math.max(V.hi,THEIRS)+.05)*10)/10);
 const x=t=>m+(t-lo)/(hi-lo)*(w-2*m);
 el('line',{{x1:m,x2:w-m,y1:40,y2:40,stroke:css('--line'),'stroke-width':2}},s);
 for(let t=lo;t<=hi+1e-9;t+=.1)txt(s,x(t),62,(t*100).toFixed(0)+'%',{{'text-anchor':'middle'}});
 el('rect',{{x:x(V.lo),y:34,width:Math.max(6,x(V.hi)-x(V.lo)),height:12,rx:6,fill:css('--mine'),opacity:.3}},s);
 el('circle',{{cx:x(V.share),cy:40,r:8,fill:css('--mine'),stroke:css('--surface'),'stroke-width':3}},s);
 txt(s,x(V.share),20,'mine',{{'text-anchor':'middle',class:'lbl'}});
 el('line',{{x1:x(THEIRS),x2:x(THEIRS),y1:26,y2:52,stroke:css('--theirs'),'stroke-width':3}},s);
 txt(s,x(THEIRS),20,'theirs',{{'text-anchor':'middle',class:'lbl'}});
}}
function bridge(){{
 // Label above each bar, so long labels never clip in a narrow card.
 const B=D.bridge,rh=50,[s,w]=fresh('bridge',B.length*rh),vw=58;
 const x=v=>v*(w-vw);
 B.forEach((b,i)=>{{const y=i*rh;
  txt(s,0,y+15,b.label,{{class:'lbl'}});
  el('rect',{{x:0,y:y+22,width:Math.max(2,x(b.value)),height:18,rx:4,fill:css(b.kind==='mine'?'--mine':b.kind==='theirs'?'--theirs':'--step')}},s);
  txt(s,x(b.value)+8,y+36,pct(b.value),{{class:'val'}});
 }});
}}
function hours(){{
 const H=D.hours.filter(h=>h.share!=null),[s,w]=fresh('hours',200),ml=36,mr=8,mt=8,mb=22;
 const ys=H.flatMap(h=>[h.lo??h.share,h.hi??h.share]).concat([THEIRS]);
 const y0=Math.max(0,Math.floor((Math.min(...ys)-.03)*10)/10),y1=Math.min(1,Math.ceil((Math.max(...ys)+.03)*10)/10);
 const x=h=>ml+(h+.5)/24*(w-ml-mr),y=v=>mt+(1-(v-y0)/(y1-y0))*(200-mt-mb);
 for(let t=y0;t<=y1+1e-9;t+=.1){{el('line',{{x1:ml,x2:w-mr,y1:y(t),y2:y(t),stroke:css('--line')}},s);txt(s,ml-6,y(t)+4,(t*100).toFixed(0)+'%',{{'text-anchor':'end'}})}}
 for(let h=0;h<24;h+=6)txt(s,x(h),196,String(h).padStart(2,'0')+'h',{{'text-anchor':'middle'}});
 const band=H.filter(h=>h.lo!=null);
 if(band.length>1)el('path',{{d:'M'+band.map(h=>x(h.hour_utc)+','+y(h.hi)).join('L')+'L'+band.slice().reverse().map(h=>x(h.hour_utc)+','+y(h.lo)).join('L')+'Z',fill:css('--mine'),opacity:.18}},s);
 el('line',{{x1:ml,x2:w-mr,y1:y(THEIRS),y2:y(THEIRS),stroke:css('--theirs'),'stroke-width':2,'stroke-dasharray':'6 4'}},s);
 if(H.length>1)el('path',{{d:'M'+H.map(h=>x(h.hour_utc)+','+y(h.share)).join('L'),fill:'none',stroke:css('--mine'),'stroke-width':2}},s);
 const tip=document.getElementById('tip'),box=document.getElementById('hours');
 H.forEach(h=>{{el('circle',{{cx:x(h.hour_utc),cy:y(h.share),r:4,fill:css('--mine'),stroke:css('--surface'),'stroke-width':2}},s);
  const hit=el('rect',{{x:x(h.hour_utc)-(w-ml-mr)/48,y:0,width:(w-ml-mr)/24,height:200,fill:'transparent'}},s);
  hit.onmouseenter=()=>{{tip.style.display='block';tip.style.left=(x(h.hour_utc)/w*100)+'%';tip.style.top=(y(h.share)/200*box.clientHeight)+'px';tip.textContent=String(h.hour_utc).padStart(2,'0')+':00 UTC  '+pct(h.share)}};
  hit.onmouseleave=()=>{{tip.style.display='none'}}}});
}}
function draw(){{ruler();bridge();hours()}}
label();draw();
let rt;const later=()=>{{clearTimeout(rt);rt=setTimeout(draw,120)}};
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(draw);
if(window.ResizeObserver){{let last=0;new ResizeObserver(es=>{{const w=es[0].contentRect.width|0;if(w!==last){{last=w;later()}}}}).observe(document.querySelector('main'))}}else addEventListener('resize',later);
}})();
</script></body></html>
"""

if __name__ == "__main__":
    r = json.loads((ROOT / "report/local/results.json").read_text())
    w = json.loads((ROOT / "docs/local/why_we_differ.json").read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(r, w))
    print(f"wrote {OUT}")
