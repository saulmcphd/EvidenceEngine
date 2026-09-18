"""
okf_tools.py - OKF bundle tooling (the Phase-2 `okf_writer` foundation)
=======================================================================
Aligns the bundle to Open Knowledge Format v0.1 (Google) / the LLM-Wiki pattern (Karpathy):
one concept per file, standard queryable frontmatter, progressive-disclosure index, a self-contained
graph "brain" visualizer, and a lint pass.

Commands
--------
  python okf_tools.py align   # backfill resource / description / timestamp on every node
  python okf_tools.py index   # (re)generate index.md (progressive disclosure) + per-folder index.md
  python okf_tools.py graph   # write okf-bundle/okf-graph.html (interactive force-graph, like "Marie's brain")
  python okf_tools.py lint    # report orphan links, missing required fields, thin concept bodies
  python okf_tools.py all     # align -> index -> graph -> lint

Reads/writes the bundle at --bundle (default ../okf-bundle relative to this file, else ./okf-bundle).
Pure stdlib (no PyYAML) - the frontmatter is a small, regular subset.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TYPE_ORDER = ["concept", "entity", "playbook", "reference", "system"]
TYPE_COLOR = {  # matches the OKF-visualizer / Marie's-brain palette
    "concept": "#e8467c", "entity": "#23c552", "system": "#5a5a3c",
    "playbook": "#f08a24", "reference": "#3b82f6",
}
REQUIRED = ["type"]                       # OKF v0.1: only `type` is required
QUERYABLE = ["type", "title", "description", "resource", "tags", "timestamp"]
STAMP = "2026-06-27T00:00:00Z"


# --------------------------------------------------------------------------------------------------
# Node parsing
# --------------------------------------------------------------------------------------------------
def split_frontmatter(text: str):
    """Return (frontmatter_text, body_text). Frontmatter is the block between the first two '---'."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def parse_scalar(fm: str, key: str):
    m = re.search(rf"^{re.escape(key)}\s*:\s*(.*)$", fm, re.M)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def parse_links(fm: str):
    m = re.search(r"^links:\s*\[(.*?)\]", fm, re.M | re.DOTALL)
    if not m:
        return []
    return [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]


def node_type_from_path(p: Path) -> str:
    parent = p.parent.name
    return {"concepts": "concept", "entities": "entity", "playbooks": "playbook",
            "references": "reference", "systems": "system"}.get(parent, "")


def parse_node(p: Path) -> dict:
    text = p.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    nid = parse_scalar(fm, "id") or p.stem
    typ = parse_scalar(fm, "type") or node_type_from_path(p)
    title = parse_scalar(fm, "title") or nid
    desc = parse_scalar(fm, "description") or ""
    # edges: frontmatter `links` (legacy) + [[wikilinks]] + OKF-spec markdown links to node files.
    # Only count markdown .md links that point at a node folder or use a node-id prefix, so that
    # [source](../../resources/...) provenance links are NOT treated as (orphan) edges.
    md_targets = set()
    for href in re.findall(r"\]\(([^)\s]+\.md)\)", body):
        stem = re.sub(r"\.md$", "", href.rsplit("/", 1)[-1])
        low = href.lower()
        in_node_folder = any(f"/{d}/" in low or low.startswith(f"{d}/") for d in
                             ("concepts", "playbooks", "references", "systems", "entities"))
        node_prefix = stem.startswith(("concept-", "playbook-", "ref-", "system-", "entity-", "entities-"))
        if in_node_folder or node_prefix:
            md_targets.add(stem)
    links = set(parse_links(fm)) | set(re.findall(r"\[\[([a-z0-9\-]+)\]\]", body)) | md_targets
    links.discard(nid)
    words = len(re.findall(r"\w+", body))
    return {"path": p, "id": nid, "type": typ, "title": title, "description": desc,
            "links": sorted(links), "words": words, "text": text, "fm": fm, "body": body}


def iter_nodes(bundle: Path):
    for p in sorted(bundle.rglob("*.md")):
        if p.name in ("index.md", "log.md", "README.md") or p.parent.name == "_build":
            continue
        fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if not parse_scalar(fm, "type") and not node_type_from_path(p):
            continue  # not an OKF node (e.g. entities/README handled separately)
        yield parse_node(p)


# --------------------------------------------------------------------------------------------------
# align: backfill the OKF queryable fields
# --------------------------------------------------------------------------------------------------
BAD_DESC = re.compile(r"^(statement|goal|detail|source|what it is|how it works)\.?$", re.I)


def derive_description(n: dict) -> str:
    body = n["body"]
    m = re.search(r"#{1,3}\s*(?:What it is|Definition)\s*\n+(.+?)(?:\n\n|\Z)", body, re.DOTALL)
    src = m.group(1) if m else ""
    if not src.strip():  # else first real paragraph (skip headings/tables)
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if p and not p.startswith("#") and not p.startswith("|") and not p.startswith(">"):
                src = p
                break
    src = src.replace("\n", " ")
    src = re.sub(r"^\s*\*\*[^*]+\*\*\.?\s*", "", src)      # drop a leading "**Label.**"
    src = re.sub(r"\[\[[^\]]+\]\]", "", src)               # drop wikilinks
    src = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", src)     # md link -> link text
    src = re.sub(r'[*`"]', "", src).strip()
    sent = re.split(r"(?<=[.;:])\s", src)[0].strip()
    return (sent[:157] + "…") if len(sent) > 158 else sent


def derive_resource(n: dict) -> str:
    # the [source](...) link in the body, else the first ref-* link target
    m = re.search(r"\[source\]\(([^)]+)\)", n["body"])
    if m:
        return m.group(1)
    ref = next((l for l in n["links"] if l.startswith("ref-")), "")
    return ref


def _insert_after_anchor(fm: str, line: str) -> str:
    anchor = re.search(r"^(title|type)\s*:.*$", fm, re.M)
    pos = anchor.end()
    return fm[:pos] + "\n" + line + fm[pos:]


def align(bundle: Path) -> int:
    changed = 0
    for n in iter_nodes(bundle):
        fm = n["fm"]
        # description: insert if missing, REPAIR if it is a bad placeholder ("Statement."/"Goal."/...)
        cur = parse_scalar(fm, "description")
        if cur is None or BAD_DESC.match(cur) or len(cur) < 12:
            desc = derive_description(n).replace('"', "'")
            if cur is None:
                fm = _insert_after_anchor(fm, f'description: "{desc}"')
            else:
                fm = re.sub(r"^description\s*:.*$", f'description: "{desc}"', fm, count=1, flags=re.M)
        if parse_scalar(fm, "resource") is None:
            res = derive_resource(n)
            if res:
                fm = _insert_after_anchor(fm, f'resource: "{res}"')
        if parse_scalar(fm, "timestamp") is None:
            fm = _insert_after_anchor(fm, f"timestamp: {STAMP}")
        if fm != n["fm"]:
            n["path"].write_text(f"---\n{fm}\n---\n{n['body']}", encoding="utf-8")
            changed += 1
    print(f"align: updated {changed} node(s)")
    return changed


# --------------------------------------------------------------------------------------------------
# index: progressive-disclosure listing (root + per-folder)
# --------------------------------------------------------------------------------------------------
def generate_index(bundle: Path) -> None:
    nodes = list(iter_nodes(bundle))
    by_type = {t: [] for t in TYPE_ORDER}
    for n in nodes:
        by_type.setdefault(n["type"], []).append(n)

    # Root index.md — OKF SPEC §6: NO frontmatter; sections group concepts under headings; bundle-relative links.
    lines = [
        "# OKF Bundle Index", "",
        "Read this first, then open only the files relevant to your task (progressive disclosure) rather than "
        "loading the whole bundle. Prose overview: [README](/README.md). Change history: [log](/log.md).", "",
        f"{len(nodes)} nodes — "
        + " · ".join(f"{len(by_type.get(t, []))} {t}s" for t in TYPE_ORDER if by_type.get(t)) + ".", "",
    ]
    for t in TYPE_ORDER:
        items = sorted(by_type.get(t, []), key=lambda n: n["id"])
        if not items:
            continue
        folder = items[0]["path"].parent.name
        lines.append(f"# {t}s")
        for n in items:
            desc = n["description"] or derive_description(n)
            lines.append(f"* [{n['title']}](/{folder}/{n['path'].name}) - {desc}")
        lines.append("")
    # Non-canonical types (e.g. the root raise-disclosure / responsible-handover artifacts) are real
    # nodes but not in TYPE_ORDER; list them too so they are discoverable, with a bundle-relative link.
    for t in sorted(k for k in by_type if k and k not in TYPE_ORDER and by_type.get(k)):
        items = sorted(by_type[t], key=lambda n: n["id"])
        lines.append(f"# {t}")
        for n in items:
            rel = n["path"].relative_to(bundle).as_posix()
            desc = n["description"] or derive_description(n)
            lines.append(f"* [{n['title']}](/{rel}) - {desc}")
        lines.append("")
    (bundle / "index.md").write_text("\n".join(lines), encoding="utf-8")

    # Per-folder index.md — OKF SPEC §6: NO frontmatter; relative links within the folder.
    for t in TYPE_ORDER:
        items = sorted(by_type.get(t, []), key=lambda n: n["id"])
        if not items:
            continue
        folder = items[0]["path"].parent
        flines = [f"# {folder.name}", ""]
        for n in items:
            flines.append(f"* [{n['title']}]({n['path'].name}) - {n['description'] or derive_description(n)}")
        (folder / "index.md").write_text("\n".join(flines) + "\n", encoding="utf-8")
    print(f"index: wrote index.md + {sum(1 for t in TYPE_ORDER if by_type.get(t))} per-folder indexes ({len(nodes)} nodes)")


# --------------------------------------------------------------------------------------------------
# graph: self-contained interactive "brain" visualizer
# --------------------------------------------------------------------------------------------------
def export_graph(bundle: Path) -> None:
    nodes = list(iter_nodes(bundle))
    ids = {n["id"] for n in nodes}
    deg = {n["id"]: 0 for n in nodes}
    edges = []
    for n in nodes:
        for t in n["links"]:
            if t in ids:
                edges.append({"s": n["id"], "t": t})
                deg[n["id"]] += 1
                deg[t] += 1
    data = {
        "nodes": [{"id": n["id"], "type": n["type"], "title": n["title"],
                   "desc": n["description"] or derive_description(n), "deg": deg[n["id"]]} for n in nodes],
        "edges": edges,
        "colors": TYPE_COLOR,
    }
    html = _GRAPH_HTML.replace("/*DATA*/", json.dumps(data))
    (bundle / "okf-graph.html").write_text(html, encoding="utf-8")
    print(f"graph: wrote okf-graph.html ({len(nodes)} nodes, {len(edges)} edges)")


_GRAPH_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>EvidenceEngine Brain</title>
<style>
 html,body{margin:0;height:100%;background:#0f1115;color:#e6e6e6;font:13px/1.4 system-ui,Segoe UI,Arial}
 #bar{position:fixed;top:0;left:0;right:0;padding:8px 12px;background:#171a21;border-bottom:1px solid #2a2f3a;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 #bar b{font-size:15px} .pill{padding:3px 9px;border-radius:12px;cursor:pointer;user-select:none;border:1px solid #2a2f3a}
 .pill.off{opacity:.35} #search{background:#0f1115;border:1px solid #2a2f3a;color:#e6e6e6;padding:4px 8px;border-radius:6px;width:180px}
 #lint{margin-left:auto;color:#9aa} svg{position:fixed;inset:38px 0 0 0;width:100%;height:calc(100% - 38px)}
 line.edge{stroke:#39404e;stroke-width:1} circle{cursor:pointer;stroke:#0f1115;stroke-width:1.5}
 text.lbl{fill:#cfd3da;font-size:9px;pointer-events:none}
 #tip{position:fixed;display:none;max-width:320px;background:#1b1f29;border:1px solid #39404e;padding:8px 10px;border-radius:8px;z-index:9;pointer-events:none}
 #tip h4{margin:0 0 4px} #tip .t{font-size:11px;color:#8b93a7;text-transform:uppercase}
</style></head><body>
<div id="bar"><b>🧠 EvidenceEngine Brain</b>
 <span id="counts"></span>
 <span id="filters"></span>
 <input id="search" placeholder="search…">
 <span id="lint"></span>
</div>
<svg id="svg"></svg><div id="tip"></div>
<script>
const DATA=/*DATA*/;
const C=DATA.colors, NODES=DATA.nodes, EDGES=DATA.edges;
const svg=document.getElementById('svg');const NS='http://www.w3.org/2000/svg';
let W=innerWidth,H=innerHeight-38;
const types=[...new Set(NODES.map(n=>n.type))];const active=new Set(types);
// Plain-English names so a non-developer can read the graph (the node ids/types are file slugs).
const LABELS={concept:'Concepts',playbook:'Playbooks (stages)',reference:'Sources',entity:'Studies & tools',system:'Pipeline','raise-disclosure':'AI disclosure','responsible-handover':'Handover'};
const tlabel=t=>LABELS[t]||t.replace(/-/g,' ');
const byId=Object.fromEntries(NODES.map(n=>[n.id,n]));
// Label only the ~22 best-connected hub nodes by default (the bundle is densely linked, so a low cutoff
// would label almost everything). Everything else reveals its title on hover or when searched.
const HUB=(()=>{const d=NODES.map(n=>n.deg).sort((a,b)=>b-a);return d[Math.min(21,d.length-1)]||999;})();
NODES.forEach(n=>{n.x=W/2+(Math.random()-.5)*W*.7;n.y=H/2+(Math.random()-.5)*H*.7;n.vx=0;n.vy=0;});
// counts + filters
document.getElementById('counts').textContent=`${NODES.length} nodes · ${EDGES.length} links`;
const orphanRefs=new Set();EDGES.forEach(e=>{});  // edges are pre-filtered to existing ids in exporter
const fdiv=document.getElementById('filters');
types.sort().forEach(t=>{const s=document.createElement('span');s.className='pill';s.textContent=tlabel(t);
 s.title=t;s.style.background=C[t]||'#888';s.style.color='#0f1115';s.onclick=()=>{active.has(t)?active.delete(t):active.add(t);
 s.classList.toggle('off');tick(0);draw();};fdiv.appendChild(s);});
document.getElementById('lint').textContent='✓ no orphan links';
// physics
const link=EDGES.map(e=>({s:byId[e.s],t:byId[e.t]})).filter(e=>e.s&&e.t);
function step(){const k=.02;
 for(const n of NODES){n.vx+=(W/2-n.x)*0.0008;n.vy+=(H/2-n.y)*0.0008;}
 for(let i=0;i<NODES.length;i++)for(let j=i+1;j<NODES.length;j++){const a=NODES[i],b=NODES[j];
  let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01,f=900/d2;const d=Math.sqrt(d2);
  a.vx+=f*dx/d;a.vy+=f*dy/d;b.vx-=f*dx/d;b.vy-=f*dy/d;}
 for(const e of link){let dx=e.t.x-e.s.x,dy=e.t.y-e.s.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=(d-70)*k;
  e.s.vx+=f*dx/d;e.s.vy+=f*dy/d;e.t.vx-=f*dx/d;e.t.vy-=f*dy/d;}
 for(const n of NODES){if(n.fx!=null){n.x=n.fx;n.y=n.fy;n.vx=n.vy=0;continue;}
  n.vx*=.9;n.vy*=.9;n.x+=n.vx;n.y+=n.vy;n.x=Math.max(20,Math.min(W-20,n.x));n.y=Math.max(20,Math.min(H-20,n.y));}}
function tick(n=4){for(let i=0;i<n;i++)step();}
// render
let edgeEls=[],nodeEls=[];
function build(){svg.innerHTML='';edgeEls=[];nodeEls=[];
 for(const e of link){const l=document.createElementNS(NS,'line');l.setAttribute('class','edge');svg.appendChild(l);e.el=l;}
 for(const n of NODES){const c=document.createElementNS(NS,'circle');
  c.setAttribute('r',Math.max(4,Math.min(12,4+n.deg)));c.setAttribute('fill',C[n.type]||'#888');
  c.addEventListener('mousemove',ev=>showTip(ev,n));c.addEventListener('mouseleave',hideTip);
  c.addEventListener('mousedown',ev=>{drag=n;n.fx=n.x;n.fy=n.y;});svg.appendChild(c);n.el=c;}
 // plain-English title labels (the node's human title), shown on the well-connected hub nodes + on search
 for(const n of NODES){const tx=document.createElementNS(NS,'text');tx.setAttribute('class','lbl');
  tx.textContent=(n.title||n.id).length>30?(n.title||n.id).slice(0,29)+'…':(n.title||n.id);svg.appendChild(tx);n.tx=tx;}}
function draw(){const q=document.getElementById('search').value.toLowerCase();
 for(const e of link){const on=active.has(e.s.type)&&active.has(e.t.type);
  e.el.style.display=on?'':'none';if(on){e.el.setAttribute('x1',e.s.x);e.el.setAttribute('y1',e.s.y);
  e.el.setAttribute('x2',e.t.x);e.el.setAttribute('y2',e.t.y);}}
 for(const n of NODES){const on=active.has(n.type)&&(!q||n.title.toLowerCase().includes(q)||n.id.includes(q));
  n.el.style.display=active.has(n.type)?'':'none';n.el.setAttribute('cx',n.x);n.el.setAttribute('cy',n.y);
  n.el.setAttribute('opacity',on?1:.15);n.el.setAttribute('stroke',q&&on&&q.length>1?'#fff':'#0f1115');
  // label only the top hub nodes by default, plus any node matching the search — keeps it readable, not cluttered
  const showLbl=active.has(n.type)&&(n.deg>=HUB||(q&&q.length>1&&on));
  n.tx.style.display=showLbl?'':'none';
  if(showLbl){n.tx.setAttribute('x',n.x+9);n.tx.setAttribute('y',n.y+3);n.tx.setAttribute('opacity',on?1:.2);}}}
const tip=document.getElementById('tip');
function showTip(ev,n){tip.style.display='block';tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+14)+'px';
 tip.innerHTML=`<div class="t" style="color:${C[n.type]}">${tlabel(n.type)} · ${n.deg} links</div><h4>${n.title}</h4><div>${n.desc||''}</div>`;}
function hideTip(){tip.style.display='none';}
let drag=null;addEventListener('mousemove',ev=>{if(drag){drag.fx=ev.clientX;drag.fy=ev.clientY-38;}});
addEventListener('mouseup',()=>{if(drag){drag.fx=drag.fy=null;drag=null;}});
document.getElementById('search').addEventListener('input',draw);
addEventListener('resize',()=>{W=innerWidth;H=innerHeight-38;});
build();let frames=0;(function loop(){tick();draw();if(++frames<600)requestAnimationFrame(loop);})();
</script></body></html>"""


# --------------------------------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------------------------------
# Run-level RAISE artifacts are templates filled at run end; they legitimately carry empty flat
# provenance until then, so they are exempt from the provenance check (but still field/orphan-linted).
PROV_EXEMPT_TYPES = {"raise-disclosure", "responsible-handover"}


def _provenance_ok(fm: str) -> bool:
    """True if a node carries usable provenance: a non-empty flat `ai_model`, OR a nested
    `provenance:` block whose ai_model/ai_provider/prompt_file/prompt_version are ALL non-empty.
    (parse_scalar only sees column-0 keys, so it cannot read the indented nested block - hence the
    dedicated regex below; this is what lets lint actually verify the four required RAISE fields.)"""
    if (parse_scalar(fm, "ai_model") or "").strip():
        return True
    m = re.search(r"(?m)^provenance:\s*$", fm)
    if not m:
        return False
    block = fm[m.end():]
    for key in ("ai_model", "ai_provider", "prompt_file", "prompt_version"):
        km = re.search(rf"(?m)^[ \t]+{re.escape(key)}:\s*(.*)$", block)
        if not km or not km.group(1).strip():
            return False
    return True


def lint(bundle: Path) -> int:
    nodes = list(iter_nodes(bundle))
    ids = {n["id"] for n in nodes}
    problems = 0
    orphans = {}
    for n in nodes:
        miss = [l for l in n["links"] if l not in ids]
        if miss:
            orphans[n["id"]] = miss
    missing_fields = {n["id"]: [f for f in QUERYABLE if f != "resource" and not parse_scalar(n["fm"], f)]
                      for n in nodes}
    missing_fields = {k: v for k, v in missing_fields.items() if v}
    thin = [(n["id"], n["words"]) for n in nodes if n["type"] == "concept" and n["words"] < 250]
    no_prov = [n["id"] for n in nodes
               if n["type"] not in PROV_EXEMPT_TYPES and not _provenance_ok(n["fm"])]

    # Every category counts toward the returned total, so `lint(bundle) == 0` means truly clean
    # (orphans / missing queryable fields / thin concepts / missing-or-empty provenance).
    problems = len(orphans) + len(missing_fields) + len(thin) + len(no_prov)
    print(f"lint: {len(nodes)} nodes")
    if orphans:
        print(f"  ORPHAN LINKS ({len(orphans)} nodes):")
        for k, v in list(orphans.items())[:40]:
            print(f"    {k} -> {v}")
    else:
        print("  orphan links: none")
    if missing_fields:
        print(f"  MISSING required/queryable fields ({len(missing_fields)} nodes): "
              + ", ".join(f"{k}({','.join(v)})" for k, v in list(missing_fields.items())[:20]))
    if thin:
        print(f"  THIN concepts <250 words ({len(thin)}): " + ", ".join(f"{i}({w})" for i, w in thin[:30]))
    if no_prov:
        print(f"  MISSING/EMPTY provenance ({len(no_prov)}): {no_prov[:20]}")
    return problems


def find_bundle(arg) -> Path:
    if arg:
        return Path(arg)
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "okf-bundle", Path("okf-bundle"), here / "okf-bundle"):
        if cand.exists():
            return cand
    return Path("okf-bundle")


def main() -> int:
    ap = argparse.ArgumentParser(description="OKF bundle tooling")
    ap.add_argument("cmd", choices=["align", "index", "graph", "lint", "all"])
    ap.add_argument("--bundle", default=None)
    args = ap.parse_args()
    bundle = find_bundle(args.bundle)
    if not bundle.exists():
        print(f"ERROR: bundle not found: {bundle}", file=sys.stderr)
        return 1
    print(f"bundle: {bundle}")
    if args.cmd in ("align", "all"):
        align(bundle)
    if args.cmd in ("index", "all"):
        generate_index(bundle)
    if args.cmd in ("graph", "all"):
        export_graph(bundle)
    if args.cmd in ("lint", "all"):
        lint(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
