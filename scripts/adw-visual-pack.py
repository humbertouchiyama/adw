#!/usr/bin/env python3
"""adw-visual-pack.py: build the design sign-off pack of adw-build §3.2a, one HTML page for a whole run.

  python3 adw-visual-pack.py --pack <dir> --manifest <manifest.json>

The run calls it once, after every unit is built, when `repo-profile §23` Sign-off is `end of run`, and
again after each note the owner sends. It copies every image the manifest names into `<dir>/img/`, writes
`<dir>/index.html` and `<dir>/.gitignore` (`*`, so the pack never shows in `git status`), and prints
`pack <dir>/index.html · <u> units · <r> rows · <i> images · <m> missing`. Exit 0; 1 when the manifest is
unreadable or a field is wrong (it prints `pack failed — <why>` and writes nothing); 2 on a bad flag.

The page shows, for each unit: its title and plain summary, how it was checked (lines copied from its PR's
evidence block), the RMSE table (id · state · crop · RMSE · limit · result), then each state it names as
three images side by side, before (the fork point), after (the verified head) and goal (the design), with
each row's crop drawn on them, and each row's crop zoomed at one scale. It ends with the one sign-off
question. A missing image is shown as `no image`, never left out.

Manifest (JSON). Every path is absolute. `before`, `after` and `goal` may be `none`, the verifier's word
for an image that does not exist (adw-build §3.4: a state new at the fork point is `before none`): the
page says why, and `none` is not counted as missing. "" or a path this machine does not have is
`no image`, counted as missing:

  {"slug": "<slug>", "title": "<intent title>", "contract": "<sha7>", "round": 1, "note": "",
   "prs": ["#105 final PR · ready · gates green · review clean"],
   "units": [{"unit": "u4", "title": "<unit title>", "summary": "<plain words>",
              "checks": ["<evidence row, verbatim>", ...],
              "rows": [{"id": "V1", "state": "<state>", "crop": "x,y,w,h", "design_crop": "",
                        "rmse": "0.1735", "limit": "baseline", "result": "unscored", "graded": "#105 v2",
                        "before": "<path>", "after": "<path>", "goal": "<design path; '' for a G row>"}]}]}
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time

CROP = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")
ID = re.compile(r"^[VG]\d+$")
NONE = "none"  # the image does not exist, by the verifier's word: never a pack-relative path ("img/...")
WHY = {"before": "new in this run: the fork point has no such screen",
       "after": "not rendered at the verified head", "goal": "no design image"}


class Bad(Exception):
    pass


def crop(text: str, where: str) -> list[int]:
    m = CROP.match(str(text))
    if not m:
        raise Bad("%s: crop %r is not x,y,w,h" % (where, text))
    c = [int(v) for v in m.groups()]
    if c[2] == 0 or c[3] == 0:
        raise Bad("%s: crop %r has a zero width or height" % (where, text))
    return c


def need(obj: dict, key: str, where: str, kind=str):
    if key not in obj or not isinstance(obj[key], kind) or (kind is str and not obj[key].strip()):
        raise Bad("%s: %s is missing or empty" % (where, key))
    return obj[key]


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        raise Bad("manifest %s: %s" % (path, e))
    if not isinstance(m, dict):
        raise Bad("manifest: not a JSON object")
    need(m, "slug", "manifest")
    units = need(m, "units", "manifest", list)
    if not units:
        raise Bad("manifest: units is empty")
    for u in units:
        where = "unit %s" % u.get("unit", "?") if isinstance(u, dict) else "a unit"
        if not isinstance(u, dict):
            raise Bad("%s: not an object" % where)
        for k in ("unit", "title", "summary"):
            need(u, k, where)
        rows = need(u, "rows", where, list)
        if not rows:
            raise Bad("%s: rows is empty" % where)
        for r in rows:
            if not isinstance(r, dict):
                raise Bad("%s: a row is not an object" % where)
            rid = need(r, "id", where)
            if not ID.match(rid):
                raise Bad("%s: row id %r is not V<n> or G<n>" % (where, rid))
            rw = "%s %s" % (u["unit"], rid)
            need(r, "state", rw)
            need(r, "result", rw)
            r["_crop"] = crop(r.get("crop", ""), rw)
            r["_dcrop"] = crop(r["design_crop"], rw) if str(r.get("design_crop", "")).strip() else r["_crop"]
            for k in ("before", "after", "goal", "rmse", "limit", "graded", "design_crop"):
                if not isinstance(r.get(k, ""), str):
                    raise Bad("%s: %s is not a string" % (rw, k))
        if not isinstance(u.get("checks", []), list):
            raise Bad("%s: checks is not a list" % where)
    return m


class Images:
    """Copies each source image once into <pack>/img/<unit>/<kind>/ and returns its pack-relative path."""

    def __init__(self, pack: str):
        self.pack, self.done, self.copied, self.missing = pack, {}, 0, 0

    def add(self, unit: str, kind: str, src: str) -> str | None:
        if src.strip().lower() == NONE:
            return NONE
        if not src:
            self.missing += 1
            return None
        key = (unit, kind, src)
        if key in self.done:
            if self.done[key] is None:
                self.missing += 1
            return self.done[key]
        if not os.path.isfile(src):
            self.missing += 1
            self.done[key] = None
            return None
        stem, ext = os.path.splitext(os.path.basename(src))
        tag = hashlib.sha1(src.encode("utf-8")).hexdigest()[:6]
        rel = "img/%s/%s/%s-%s%s" % (safe(unit), kind, safe(stem), tag, ext.lower() or ".png")
        dst = os.path.join(self.pack, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        self.copied += 1
        self.done[key] = rel
        return rel


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "x"


def cls(result: str) -> str:
    r = result.strip().lower()
    return {"pass": "pass", "fail": "fail", "unscored": "unscored", "no image": "noimage"}.get(r, "other")


e = html.escape


def blank(label: str, rel: str | None) -> str:
    return e(WHY.get(label, "no image")) if rel == NONE else "no image"


def shot(label: str, rel: str | None, src: str, boxes: list[dict], note: str = "") -> str:
    cap = "<figcaption><b>%s</b>%s<code>%s</code></figcaption>" % (
        e(label), (" · " + e(note)) if note else "", e(src or "no path") if rel != NONE else "")
    if rel is None or rel == NONE:
        return '<figure class="shot"><div class="missing">%s</div>%s</figure>' % (blank(label, rel), cap)
    return ('<figure class="shot"><a class="frame" href="%s" target="_blank">'
            '<img loading="lazy" src="%s" alt="%s" data-boxes=\'%s\'></a>%s</figure>'
            % (e(rel), e(rel), e(label), e(json.dumps(boxes)), cap))


def zoom(label: str, rel: str | None, c: list[int]) -> str:
    if rel is None or rel == NONE:
        return ('<figure class="zoom"><div class="missing">%s</div><figcaption>%s</figcaption></figure>'
                % (blank(label, rel), e(label)))
    return ('<figure class="zoom"><div class="crop" style="aspect-ratio:%d / %d">'
            '<img loading="lazy" src="%s" alt="%s" data-crop="%d,%d,%d,%d"></div><figcaption>%s</figcaption></figure>'
            % (c[2], c[3], e(rel), e(label), c[0], c[1], c[2], c[3], e(label)))


def pick(srows: list[dict], kind: str) -> tuple[str | None, str]:
    """The state's image of one kind: a copied image first, then `none`, then a missing one."""
    rank = lambda r: 0 if r["_" + kind] not in (None, NONE) else 1 if r["_" + kind] == NONE else 2 if r.get(kind) else 3
    best = min(srows, key=rank)
    return (best["_" + kind], best.get(kind, "")) if rank(best) < 3 else (None, "")


def unit_html(u: dict, imgs: Images) -> tuple[str, dict]:
    counts = {"pass": 0, "fail": 0, "unscored": 0, "noimage": 0, "other": 0}
    rows = u["rows"]
    for r in rows:
        counts[cls(r["result"])] += 1
        r["_before"] = imgs.add(u["unit"], "before", r.get("before", ""))
        r["_after"] = imgs.add(u["unit"], "after", r.get("after", ""))
        r["_goal"] = imgs.add(u["unit"], "goal", r.get("goal", "")) if r["id"].startswith("V") else None
    out = ['<section class="unit" id="%s">' % e(safe(u["unit"])),
           "<h2>%s · %s</h2>" % (e(u["unit"]), e(u["title"])),
           '<p class="summary">%s</p>' % e(u["summary"])]
    checks = [c for c in u.get("checks", []) if isinstance(c, str) and c.strip()]
    if checks:
        out.append("<h3>How it was checked</h3><ul class=\"checks\">%s</ul>"
                   % "".join("<li><code>%s</code></li>" % e(c) for c in checks))
    out.append("<h3>Rows</h3><table><thead><tr><th>id</th><th>state</th><th>crop</th><th>RMSE</th>"
               "<th>limit</th><th>result</th><th>graded on</th></tr></thead><tbody>")
    for r in rows:
        out.append('<tr><td><a href="#%s-%s">%s</a></td><td>%s</td><td><code>%s</code>%s</td><td>%s</td><td>%s</td>'
                   '<td><span class="badge %s">%s</span></td><td>%s</td></tr>'
                   % (e(safe(u["unit"])), e(r["id"]), e(r["id"]), e(r["state"]), e(r["crop"]),
                      (' <small>design @<code>%s</code></small>' % e(r["design_crop"])) if str(r.get("design_crop", "")).strip() else "",
                      e(r.get("rmse", "") or "—"), e(r.get("limit", "") or "—"), cls(r["result"]), e(r["result"]),
                      e(r.get("graded", "") or "—")))
    out.append("</tbody></table>")
    states: list[str] = []
    for r in rows:
        if r["state"] not in states:
            states.append(r["state"])
    for s in states:
        srows = [r for r in rows if r["state"] == s]
        box = lambda r, dc=False: {"id": r["id"], "c": r["_dcrop"] if dc else r["_crop"], "r": cls(r["result"]),
                                   "g": r["id"].startswith("G")}
        first = srows[0]
        before_rel, before_src = pick(srows, "before")
        after_rel, after_src = pick(srows, "after")
        out.append('<div class="state"><h3>State <code>%s</code></h3><div class="trio">' % e(s))
        out.append(shot("before", before_rel, before_src, [box(r) for r in srows], "fork point"))
        out.append(shot("after", after_rel, after_src, [box(r) for r in srows], "verified head"))
        goals = []
        for r in srows:
            if r["id"].startswith("V") and r.get("goal", "") not in [g[0] for g in goals]:
                goals.append((r.get("goal", ""), r["_goal"], [box(x, True) for x in srows
                                                              if x["id"].startswith("V") and x.get("goal", "") == r.get("goal", "")]))
        if goals:
            out.append('<div class="goals">%s</div>' % "".join(shot("goal", rel, src, bx, "design") for src, rel, bx in goals))
        else:
            out.append('<figure class="shot"><div class="missing guardonly">guard rows only: the goal is the before '
                       'image, this area must not change</div><figcaption><b>goal</b></figcaption></figure>')
        out.append("</div>")
        for r in srows:
            guard = r["id"].startswith("G")
            head = "%s · <code>%s</code>%s · RMSE %s · limit %s · <span class=\"badge %s\">%s</span>" % (
                e(r["id"]), e(r["crop"]),
                (" (design @<code>%s</code>)" % e(r["design_crop"])) if str(r.get("design_crop", "")).strip() else "",
                e(r.get("rmse", "") or "—"), e(r.get("limit", "") or "—"), cls(r["result"]), e(r["result"]))
            out.append('<div class="row" id="%s-%s"><p>%s%s</p><div class="trio">' % (
                e(safe(u["unit"])), e(r["id"]), head, " · guard: must match before" if guard else ""))
            out.append(zoom("before", r["_before"], r["_crop"]))
            out.append(zoom("after", r["_after"], r["_crop"]))
            if guard:
                out.append('<figure class="zoom"><div class="missing guardonly">= before</div><figcaption>goal</figcaption></figure>')
            else:
                out.append(zoom("goal", r["_goal"], r["_dcrop"]))
            out.append("</div></div>")
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out), counts


CSS = """
:root{--bg:#fbfbf9;--fg:#1c1c1a;--mut:#6b6b66;--line:#deded8;--card:#fff;--pass:#1f7a3a;--fail:#b3261e;
--uns:#9a6700;--noi:#6b6b66;--oth:#3b5bab}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--mut:#a3a39d;--line:#34342f;--card:#1f1f1d;
--pass:#5cc27a;--fail:#ff8a80;--uns:#e3b341;--noi:#a3a39d;--oth:#8fa8ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:1500px;margin:0 auto;padding:16px}h1{font-size:24px;margin:8px 0}h2{font-size:20px;margin:32px 0 4px;
padding-top:16px;border-top:2px solid var(--line)}h3{font-size:15px;margin:20px 0 8px}code{font:12px ui-monospace,Menlo,monospace}
.meta,.summary{color:var(--mut)}.summary{font-size:16px;color:var(--fg)}table{border-collapse:collapse;width:100%;
font-size:13px}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line)}
.badge{display:inline-block;padding:0 8px;border-radius:9px;font-size:12px;font-weight:600;color:#fff}
.badge.pass{background:var(--pass)}.badge.fail{background:var(--fail)}.badge.unscored{background:var(--uns)}
.badge.noimage{background:var(--noi)}.badge.other{background:var(--oth)}
.trio{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.goals{display:grid;gap:12px}
@media (max-width:700px){.trio{grid-template-columns:1fr}}
figure{margin:0}.shot .frame{position:relative;display:inline-block;max-width:100%;border:1px solid var(--line);background:var(--card)}
.shot img{display:block;max-width:100%;width:auto;height:auto;max-height:min(70vh,640px)}a{color:var(--oth)}figcaption{font-size:12px;color:var(--mut);word-break:break-all;margin-top:4px}
figcaption b{color:var(--fg);margin-right:4px}figcaption code{display:block}
.box{position:absolute;border:2px solid var(--oth);font:600 11px ui-monospace,Menlo,monospace;color:#fff;pointer-events:none}
.box.pass{border-color:var(--pass)}.box.fail{border-color:var(--fail)}.box.unscored{border-color:var(--uns)}
.box.noimage{border-color:var(--noi)}.box.guard{border-style:dashed}
.box span{position:absolute;left:-2px;top:-2px;padding:0 4px;background:inherit}
.box.pass span{background:var(--pass)}.box.fail span{background:var(--fail)}.box.unscored span{background:var(--uns)}
.box.noimage span{background:var(--noi)}.box.other span{background:var(--oth)}
.row{margin:12px 0 20px}.row p{margin:4px 0}.crop{position:relative;overflow:hidden;border:1px solid var(--line);background:var(--card)}
.crop img{position:absolute;max-width:none;height:auto}
.missing{display:flex;align-items:center;justify-content:center;min-height:120px;border:1px dashed var(--line);
color:var(--mut);font-size:13px;padding:8px;text-align:center}
.prs li,.checks li{margin:2px 0}.note{border-left:4px solid var(--uns);padding:8px 12px;background:var(--card)}
.ask{margin:40px 0 24px;padding:16px;border:2px solid var(--fg);background:var(--card)}.ask h2{border:0;margin:0;padding:0}
"""

JS = """
function place(i){var w=i.naturalWidth,h=i.naturalHeight;if(!w)return;JSON.parse(i.dataset.boxes||'[]').forEach(function(b){
var d=document.createElement('div');d.className='box '+b.r+(b.g?' guard':'');d.style.left=(b.c[0]/w*100)+'%';
d.style.top=(b.c[1]/h*100)+'%';d.style.width=(b.c[2]/w*100)+'%';d.style.height=(b.c[3]/h*100)+'%';
var s=document.createElement('span');s.textContent=b.id;d.appendChild(s);i.parentNode.appendChild(d);});}
function zoom(i){var w=i.naturalWidth,c=i.dataset.crop.split(',').map(Number);if(!w)return;
i.style.width=(w/c[2]*100)+'%';i.style.left=(-c[0]/c[2]*100)+'%';i.style.top=(-c[1]/c[3]*100)+'%';}
function on(sel,f){document.querySelectorAll(sel).forEach(function(i){if(i.complete)f(i);else i.addEventListener('load',function(){f(i);});});}
on('img[data-boxes]',place);on('img[data-crop]',zoom);
"""

ASK = """<section class="ask"><h2>Sign-off: one answer for the whole run</h2>
<ul><li><b><code>ok</code></b>: every row that is not <code>pass</code> and not <code>no image</code> takes its measured RMSE
times 1.05 (at least 0.0001, rounded up to 4 decimals) as its limit, in one <code>docs(spec): visual limits</code> commit
per PR. Each PR is verified again, then goes on to its merge.</li>
<li><b>Anything else is a note.</b> Name the unit it is for (<code>u4: the title bar sits 8 px too low</code>). The run
fixes those units, runs their compare and gates again, and sends you a new pack.</li></ul></section>"""


def build(pack: str, m: dict) -> tuple[str, dict]:
    os.makedirs(pack, exist_ok=True)
    with open(os.path.join(pack, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("*\n")
    imgs = Images(pack)
    total = {"pass": 0, "fail": 0, "unscored": 0, "noimage": 0, "other": 0}
    parts = []
    for u in m["units"]:
        body, c = unit_html(u, imgs)
        parts.append(body)
        for k in total:
            total[k] += c[k]
    nrows = sum(total.values())
    title = m.get("title") or m["slug"]
    head = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>%s · design sign-off</title><style>%s</style></head><body><main>" % (e(title), CSS),
            "<h1>%s · design sign-off</h1>" % e(title),
            '<p class="meta"><code>%s</code> · contract <code>%s</code> · pack %s · built %s</p>' % (
                e(m["slug"]), e(str(m.get("contract", "") or "—")), e(str(m.get("round", 1))),
                e(time.strftime("%Y-%m-%d %H:%M"))),
            "<p><b>%d units · %d rows</b>: pass %d · fail %d · unscored %d · no image %d%s</p>" % (
                len(m["units"]), nrows, total["pass"], total["fail"], total["unscored"], total["noimage"],
                (" · other %d" % total["other"]) if total["other"] else "")]
    if str(m.get("note", "")).strip():
        head.append('<p class="note"><b>Your last note</b>: %s</p>' % e(m["note"]))
    prs = [p for p in m.get("prs", []) if isinstance(p, str) and p.strip()]
    if prs:
        head.append("<ul class=\"prs\">%s</ul>" % "".join("<li>%s</li>" % e(p) for p in prs))
    head.append("<p>Units: %s</p>" % " · ".join('<a href="#%s">%s</a>' % (e(safe(u["unit"])), e(u["unit"]))
                                                for u in m["units"]))
    page = "\n".join(head + parts + [ASK, "<script>%s</script></main></body></html>" % JS])
    out = os.path.join(pack, "index.html")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, out)
    return out, {"units": len(m["units"]), "rows": nrows, "images": imgs.copied, "missing": imgs.missing}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="adw-visual-pack.py")
    p.add_argument("--pack", required=True)
    p.add_argument("--manifest", required=True)
    a = p.parse_args(argv)
    try:
        m = load(a.manifest)
        out, n = build(os.path.abspath(a.pack), m)
    except (Bad, OSError) as err:
        print("pack failed — %s" % err)
        return 1
    print("pack %s · %d units · %d rows · %d images · %d missing" % (out, n["units"], n["rows"], n["images"], n["missing"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
