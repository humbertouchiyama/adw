#!/usr/bin/env python3
"""adw-visual-pack.py: build the design sign-off pack of adw-build §3.2a, one HTML page for a whole run.

  python3 adw-visual-pack.py --pack <dir> --manifest <manifest.json>

The run calls it once, after every unit is built, when `repo-profile §23` Sign-off is `end of run`, and
again after each note the owner sends. It copies every image the manifest names into `<dir>/img/`, writes
`<dir>/index.html` and `<dir>/.gitignore` (`*`, so the pack never shows in `git status`), and prints
`pack <dir>/index.html · <u> units · <r> rows · <i> images · <m> missing`. Exit 0; 1 when the manifest is
unreadable or a field is wrong (it prints `pack failed — <why>` and writes nothing); 2 on a bad flag.

The page is for a person who does not read test ids or numbers. It opens with one banner in words (which
screens differ from the design). For each unit it shows its title and plain summary, then one card per screen
(a `state`): a plain title, one verdict in words (`Matches the design`, `Differs from the design`, ...), one
line that says what to check (the rows' `check`, else the unit's summary), and then the changed areas first:
the zoomed crop of every row, After next to Design for a `V` row, Before next to After for a `G` row. The
full Before, After and Design screenshots sit in a fold below the crops, each with a box around every row's
area, labelled with its id (`V` pink, `G` blue), and buttons that show where two of them differ (a difference
blend: black is the same). Then a `Looks right` / `Needs changes` choice with a note. A screen whose rows are
all `G` rows that measured 0 difference gets no card of its own: all such screens fold into one line at the
end, `N screens unchanged`, that lists them and opens their cards. The ids, crops, RMSE numbers, limits, PR
lines and gate checks sit in folds, so they stay available but out of the way. The bottom of the page builds
the one answer to copy (`ok`, or one `<unit>: <screen>: <note>` line for each screen marked `Needs changes`).
A missing image is shown as `No image to show`, never left out.

Manifest (JSON). Every path is absolute. `before`, `after` and `goal` may be `none`, the verifier's word
for an image that does not exist (adw-build §3.4: a state new at the fork point is `before none`): the
page says why, and `none` is not counted as missing. "" or a path this machine does not have is
`no image`, counted as missing:

  {"slug": "<slug>", "title": "<intent title>", "contract": "<sha7>", "round": 1, "note": "",
   "screens": {"<state>": "<plain title, e.g. Merchant, Buy tab>"},   (optional: a state without one gets its test name in words)
   "prs": ["#105 final PR · ready · gates green · review clean"],
   "units": [{"unit": "u4", "title": "<unit title>", "summary": "<plain words>",
              "checks": ["<evidence row, verbatim>", ...],
              "rows": [{"id": "V1", "state": "<state>", "crop": "x,y,w,h", "design_crop": "",
                        "rmse": "0.1735", "limit": "baseline", "result": "unscored", "graded": "#105 v2",
                        "before": "<path>", "after": "<path>", "goal": "<design path; '' for a G row>",
                        "check": "<optional: what the owner should see there, e.g. The title reads MERCADOR>"}]}]}
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
            for k in ("before", "after", "goal", "rmse", "limit", "graded", "design_crop", "check"):
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

# One plain verdict for each (kind of row, result). The page says these, never `pass` or `RMSE`.
VERDICT = {
    ("V", "pass"): "Matches the design",
    ("V", "fail"): "Differs from the design",
    ("V", "unscored"): "Not measured: judge it by eye",
    ("V", "noimage"): "Cannot compare: an image is missing",
    ("G", "pass"): "Unchanged, as it must be",
    ("G", "fail"): "Changed, but it must not change",
    ("G", "unscored"): "Not measured: it should look the same as before",
    ("G", "noimage"): "Cannot compare: an image is missing",
}
SEVERITY = {"fail": 0, "noimage": 1, "unscored": 2, "other": 3, "pass": 4}  # the worst row names the screen
BADGE = {"fail": "bad", "noimage": "gap", "unscored": "gap", "other": "gap", "pass": "good"}


def verdict(r: dict) -> str:
    return VERDICT.get((r["id"][0], cls(r["result"])), r["result"])


def words(part: str) -> str:
    part = re.sub(r"(ScreenshotTests|Tests)$", "", part)
    part = re.sub(r"^\d+-", "", part)
    part = re.sub(r"[-_]+", " ", part)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", part).strip()


def screen_title(state: str, names: dict) -> str:
    """A plain title: the manifest's `screens` map first, else the test name in words."""
    if isinstance(names.get(state), str) and names[state].strip():
        return names[state].strip()
    return " · ".join(w for w in (words(p) for p in state.split("/") if p) if w) or state


MAXH = 420  # the tallest a zoomed crop is drawn, in CSS px


def kind(r: dict) -> str:
    return "g" if r["id"].startswith("G") else "v"


def boxes(rows: list[dict], key: str) -> str:
    """One box per distinct area of `rows` on a full screenshot, labelled with the ids of the rows that share it
    (a `V` box at its top left, a `G` box at its bottom left, so the two kinds do not cover each other's ids).
    The script sets each box in percent of the image's natural size, so it scales with the image."""
    areas: dict[tuple, list[dict]] = {}
    for r in rows:
        areas.setdefault(tuple(r[key]), []).append(r)
    return "".join('<span class="box %s" data-box="%d,%d,%d,%d" hidden><span class="ids">%s</span></span>'
                   % (kind(rs[0]), a[0], a[1], a[2], a[3],
                      "".join('<i class="tag %s">%s</i>' % (kind(r), e(r["id"])) for r in rs))
                   for a, rs in areas.items())


def shot(label: str, rel: str | None, k: str, why: str, marks: str = "") -> str:
    if rel is None or rel == NONE:
        text = why if rel == NONE else "No image to show"
        return '<figure class="shot"><figcaption><b>%s</b></figcaption><div class="missing">%s</div></figure>' % (
            e(label), e(text))
    return ('<figure class="shot"><figcaption><b>%s</b></figcaption><a class="frame" href="%s" target="_blank">'
            '<img loading="lazy" src="%s" alt="%s" data-k="%s">%s</a></figure>' % (e(label), e(rel), e(rel), e(label), k, marks))


def zoom(label: str, rel: str | None, c: list[int], why: str) -> str:
    if rel is None or rel == NONE:
        return ('<figure class="zoom"><div class="missing">%s</div><figcaption>%s</figcaption></figure>'
                % (e(why if rel == NONE else "No image to show"), e(label)))
    cap = max(1, round(min(2 * c[2], MAXH * c[2] / c[3])))  # at most twice its size, at most MAXH tall
    return ('<figure class="zoom"><div class="crop" style="aspect-ratio:%d / %d;max-width:%dpx">'
            '<img loading="lazy" src="%s" alt="%s" data-crop="%d,%d,%d,%d"></div><figcaption>%s</figcaption></figure>'
            % (c[2], c[3], cap, e(rel), e(label), c[0], c[1], c[2], c[3], e(label)))


def pick(srows: list[dict], which: str) -> str | None:
    """The state's image of one kind: a copied image first, then `none`, then a missing one."""
    rank = lambda r: 0 if r["_" + which] not in (None, NONE) else 1 if r["_" + which] == NONE else 2
    best = min(srows, key=rank)
    return best["_" + which] if rank(best) < 2 else None


def look(srows: list[dict], summary: str) -> str:
    """What the owner should check on this screen: the rows' `check` lines, else the unit's summary."""
    said: list[tuple[str, str]] = []
    for r in srows:
        c = str(r.get("check", "")).strip()
        if c and c not in [t for _, t in said]:
            said.append((r["id"], c))
    if not said:
        return summary
    if len(said) == 1:
        return said[0][1]
    return " · ".join("%s: %s" % (i, t) for i, t in said)


def unchanged(srows: list[dict]) -> bool:
    """Every row is a `G` row that measured 0 difference: the screen is the same as before."""
    def zero(t: str) -> bool:
        try:
            return float(t) == 0
        except ValueError:
            return False
    return all(r["id"].startswith("G") and cls(r["result"]) in ("pass", "unscored") and zero(str(r.get("rmse", "")))
               for r in srows)


def card(u: dict, srows: list[dict], sid: str, title: str, same: bool) -> tuple[str, str]:
    """One screen: verdict, what to check, the zoomed areas, then the full screens and the numbers in folds."""
    if same:
        badge, say = "good", "Unchanged: the same as before"
    else:
        worst = min(srows, key=lambda r: SEVERITY[cls(r["result"])])
        badge, say = BADGE[cls(worst["result"])], verdict(worst)
    before, after = pick(srows, "before"), pick(srows, "after")
    goals: list[tuple[str, str | None]] = []
    for r in srows:
        if r["id"].startswith("V") and r.get("goal", "") not in [g[0] for g in goals]:
            goals.append((r.get("goal", ""), r["_goal"]))
    out = ['<article class="screen" id="%s" data-unit="%s" data-title="%s">' % (sid, e(u["unit"]), e(title)),
           '<header><h3>%s</h3><span class="badge %s">%s</span></header>' % (e(title), badge, e(say)),
           '<p class="look"><b>Check:</b> %s</p>' % e(look(srows, u["summary"])), '<div class="areas">']
    for r in srows:
        guard, c = r["id"].startswith("G"), r["_crop"]
        out.append('<div class="area"><p><i class="tag %s">%s</i> %s</p><div class="pair%s">' % (
            kind(r), e(r["id"]), "Must not change" if guard else "Must match the design",
            " wide" if c[2] >= 1.5 * c[3] else ""))
        if guard:
            out.append(zoom("Before", r["_before"], c, "New screen: there was nothing here before"))
            out.append(zoom("After", r["_after"], c, "Not shown after the change"))
        else:
            out.append(zoom("After", r["_after"], c, "Not shown after the change"))
            out.append(zoom("Design", r["_goal"], r["_dcrop"], "No design image"))
        out.append("</div></div>")
    out.append("</div>")
    out.append('<details class="full"><summary>Full screens, with these areas boxed</summary>'
               '<p class="legend"><i class="tag v">V</i> must match the design &nbsp; <i class="tag g">G</i> must not change</p>'
               '<div class="views">')
    every = boxes(srows, "_crop")
    out.append(shot("Before", before, "before", "New screen: there was nothing here before", every))
    out.append(shot("After", after, "after", "Not shown after the change", every))
    if goals:
        for i, (src, rel) in enumerate(goals):
            mine = [r for r in srows if r["id"].startswith("V") and r.get("goal", "") == src]
            out.append(shot("Design" if len(goals) == 1 else "Design %d" % (i + 1), rel, "goal" if i == 0 else "goal%d" % (i + 1),
                            "No design image", boxes(mine, "_dcrop")))
    else:
        out.append('<figure class="shot"><figcaption><b>Design</b></figcaption><div class="missing">'
                   'No design for this screen: it must look the same as Before</div></figure>')
    out.append("</div>")
    pairs = []
    if before not in (None, NONE) and after not in (None, NONE):
        pairs.append(("Before vs After", "before", "after"))
    if goals and after not in (None, NONE) and goals[0][1] not in (None, NONE):
        pairs.append(("After vs Design", "after", "goal"))
    if pairs:
        out.append('<div class="cmp"><span>Show the differences:</span>%s<button type="button" class="cmpbtn" '
                   'data-a="off" data-b="off">Hide</button><span class="cmpnote"></span><div class="stage" hidden></div></div>'
                   % "".join('<button type="button" class="cmpbtn" data-a="%s" data-b="%s">%s</button>' % (a, b, t)
                             for t, a, b in pairs))
    out.append("</details>")
    out.append('<div class="verdict"><label><input type="radio" name="%s" value="right"> Looks right</label>'
               '<label><input type="radio" name="%s" value="wrong"> Needs changes</label>'
               '<input type="text" class="why" placeholder="What is wrong? (optional)" aria-label="What is wrong"></div>'
               % (sid, sid))
    out.append('<details><summary>Numbers</summary><div class="scroll"><table><thead><tr><th>Check</th>'
               "<th>Area (x, y, width, height)</th><th>Difference score</th><th>Allowed</th><th>Result</th>"
               "<th>Measured on</th></tr></thead><tbody>")
    for r in srows:
        what = "Must not change" if r["id"].startswith("G") else "Design"
        out.append('<tr><td>%s <small>%s</small></td><td><code>%s</code>%s</td><td>%s</td><td>%s</td>'
                   '<td><span class="badge %s">%s</span></td><td>%s</td></tr>'
                   % (e(what), e(r["id"]), e(r["crop"]),
                      (' <small>design at <code>%s</code></small>' % e(r["design_crop"])) if str(r.get("design_crop", "")).strip() else "",
                      e(r.get("rmse", "") or "—"), e(r.get("limit", "") or "—"), BADGE[cls(r["result"])],
                      e(verdict(r)), e(r.get("graded", "") or "—")))
    out.append("</tbody></table></div>")
    out.append('<p class="hint">Lower difference score means closer. "baseline" means no limit was set yet.</p>')
    out.append("</details></article>")
    return "\n".join(out), badge


def screens_html(u: dict, imgs: Images, names: dict, counter: list[int]) -> tuple[str, dict, list]:
    """The unit's section, its counts, and its unchanged screens (folded at the end of the page, not here)."""
    stats = {"fail": [], "gap": 0, "good": 0, "screens": 0}
    rows = u["rows"]
    for r in rows:
        r["_before"] = imgs.add(u["unit"], "before", r.get("before", ""))
        r["_after"] = imgs.add(u["unit"], "after", r.get("after", ""))
        r["_goal"] = imgs.add(u["unit"], "goal", r.get("goal", "")) if r["id"].startswith("V") else None
    out = ['<section class="unit" id="%s">' % e(safe(u["unit"])),
           '<h2>%s <small>%s</small></h2>' % (e(u["title"]), e(u["unit"])),
           '<p class="summary">%s</p>' % e(u["summary"])]
    states: list[str] = []
    for r in rows:
        if r["state"] not in states:
            states.append(r["state"])
    folded = []
    for s in states:
        srows = [r for r in rows if r["state"] == s]
        counter[0] += 1
        sid = "s%d" % counter[0]
        title = screen_title(s, names)
        same = unchanged(srows)
        body, badge = card(u, srows, sid, title, same)
        stats["screens"] += 1
        if badge == "bad":
            stats["fail"].append((sid, title))
        elif badge == "gap":
            stats["gap"] += 1
        else:
            stats["good"] += 1
        if same:
            folded.append((u["unit"], title, body))
        else:
            out.append(body)
    if folded and len(folded) == len(states):
        out.append('<p class="hint">Every screen of this unit is unchanged: see <a href="#same">the unchanged screens</a> at the end.</p>')
    out.append("</section>")
    return "\n".join(out), stats, folded


def same_html(folded: list) -> str:
    """One line for every unchanged screen; it opens a list, and each item opens that screen's card."""
    if not folded:
        return ""
    n = len(folded)
    return ('<section class="same" id="same"><details><summary><b>%d screen%s unchanged</b> '
            '<small>every area that must not change measured 0 difference</small></summary>%s</details></section>'
            % (n, "" if n == 1 else "s", "".join('<details class="one"><summary>%s · %s</summary>%s</details>'
                                                 % (e(unit), e(title), body) for unit, title, body in folded)))


CSS = """
:root{--bg:#fbfbf9;--fg:#1c1c1a;--mut:#6b6b66;--line:#deded8;--card:#fff;--good:#1f7a3a;--bad:#b3261e;
--gap:#9a6700;--oth:#3b5bab}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--mut:#a3a39d;--line:#34342f;--card:#1f1f1d;
--good:#5cc27a;--bad:#ff8a80;--gap:#e3b341;--oth:#8fa8ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:1400px;margin:0 auto;padding:16px}h1{font-size:26px;margin:8px 0}h2{font-size:21px;margin:40px 0 4px;
padding-top:16px;border-top:2px solid var(--line)}h2 small{font-size:12px;color:var(--mut);font-weight:400;margin-left:6px}
h3{font-size:18px;margin:0}code{font:12px ui-monospace,Menlo,monospace}small{color:var(--mut)}a{color:var(--oth)}
.summary{color:var(--fg);margin:4px 0 12px}.hint{color:var(--mut);font-size:13px}
.banner{border:2px solid var(--line);background:var(--card);border-radius:8px;padding:12px 16px;margin:12px 0}
.banner.bad{border-color:var(--bad)}.banner.good{border-color:var(--good)}.banner b{font-size:19px}.banner ul{margin:6px 0 0}
.badge{display:inline-block;padding:1px 10px;border-radius:10px;font-size:13px;font-weight:600;color:#fff}
.badge.good{background:var(--good)}.badge.bad{background:var(--bad)}.badge.gap{background:var(--gap)}
.screen{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:12px 16px;margin:14px 0}
.screen header{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin-bottom:8px}
.views{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;align-items:start}
figure{margin:0}figcaption{font-size:13px;color:var(--mut);margin:0 0 4px}figcaption b{color:var(--fg);font-size:14px}
.zoom figcaption{margin:4px 0 0}
.frame{position:relative;display:inline-block;max-width:100%;overflow:hidden;border:1px solid var(--line);background:var(--bg)}
.shot img{display:block;max-width:100%;width:auto;height:auto;max-height:min(70vh,620px)}
.missing{display:flex;align-items:center;justify-content:center;min-height:120px;border:1px dashed var(--line);
color:var(--mut);font-size:14px;padding:8px;text-align:center}
.cmp{margin:12px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}.cmp .stage{flex-basis:100%}
.cmp button{font:inherit;font-size:14px;padding:4px 12px;border:1px solid var(--line);border-radius:6px;background:var(--bg);
color:var(--fg);cursor:pointer}.cmp button.on{border-color:var(--oth);color:var(--oth);font-weight:600}
.cmpnote{font-size:13px;color:var(--mut)}
.stage{position:relative;isolation:isolate;max-width:min(100%,560px);background:#000;filter:brightness(4)}
.stage img{display:block;width:100%;height:auto}.stage img.top{position:absolute;inset:0;height:100%;mix-blend-mode:difference}
.verdict{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;margin:10px 0;padding-top:10px;border-top:1px solid var(--line)}
.verdict label{cursor:pointer}.verdict .why{flex:1 1 240px;font:inherit;font-size:14px;padding:4px 8px;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg)}
details{margin-top:6px}summary{cursor:pointer;color:var(--mut);font-size:14px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line)}
.crop{position:relative;overflow:hidden;border:1px solid var(--line);background:var(--bg)}
.crop img{position:absolute;max-width:none;height:auto}
.look{margin:2px 0 12px;font-size:17px}.areas{display:grid;gap:14px}.area p{margin:0 0 6px;font-size:14px}
.pair{display:grid;gap:10px;align-items:start;grid-template-columns:repeat(auto-fit,minmax(min(100%,120px),1fr))}
.pair.wide{grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))}
.tag{display:inline-block;font:600 12px/1.4 ui-monospace,Menlo,monospace;font-style:normal;padding:0 5px;border-radius:3px;color:#fff}
.tag.v{background:#c2185b}.tag.g{background:#0277bd}
.box{position:absolute;border:2px solid #ff3d9a;box-shadow:0 0 0 1px rgba(0,0,0,.6),inset 0 0 0 1px rgba(0,0,0,.6);pointer-events:none}
.box.g{border-color:#29b6f6}.box .ids{position:absolute;left:-2px;top:-2px;display:flex;gap:2px}
.box.g .ids{top:auto;bottom:-2px}
.box .tag{font-size:10px;padding:0 3px;border-radius:0}
details.full{margin:14px 0 0}.legend{font-size:13px;color:var(--mut);margin:6px 0 8px}.scroll{overflow-x:auto}
.same{margin:28px 0}.same>details>summary{font-size:16px;color:var(--fg)}.same .one{margin:10px 0 0}
.same .one>summary{color:var(--fg)}
@media (max-width:480px){main{padding:12px}.screen{padding:10px 12px}}
.tech{margin:24px 0}.tech li{margin:2px 0;font-size:13px}.note{border-left:4px solid var(--gap);padding:8px 12px;background:var(--card)}
.ask{margin:40px 0 24px;padding:16px;border:2px solid var(--fg);background:var(--card);border-radius:8px}.ask h2{border:0;margin:0 0 8px;padding:0}
.ask textarea{display:block;width:100%;min-height:90px;font:14px ui-monospace,Menlo,monospace;padding:8px;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg);margin:8px 0}
.ask button{font:inherit;padding:6px 16px;border:2px solid var(--fg);border-radius:6px;background:var(--fg);color:var(--bg);cursor:pointer}
"""

JS = """
function zoom(i){var w=i.naturalWidth,c=i.dataset.crop.split(',').map(Number);if(!w)return;
i.style.width=(w/c[2]*100)+'%';i.style.left=(-c[0]/c[2]*100)+'%';i.style.top=(-c[1]/c[3]*100)+'%';}
function on(sel,f){document.querySelectorAll(sel).forEach(function(i){if(i.complete&&i.naturalWidth)f(i);else i.addEventListener('load',function(){f(i);});});}
on('img[data-crop]',zoom);
function box(i){var W=i.naturalWidth,H=i.naturalHeight;if(!W)return;
i.parentNode.querySelectorAll('.box').forEach(function(b){var c=b.dataset.box.split(',').map(Number);
b.style.left=(c[0]/W*100)+'%';b.style.top=(c[1]/H*100)+'%';b.style.width=(c[2]/W*100)+'%';b.style.height=(c[3]/H*100)+'%';b.hidden=false;});}
on('.frame img',box);
document.querySelectorAll('.screen').forEach(function(sc){
var imgs={};sc.querySelectorAll('.views img[data-k]').forEach(function(i){imgs[i.dataset.k]=i;});
var stage=sc.querySelector('.stage');if(!stage)return;var note=sc.querySelector('.cmpnote');
var btns=sc.querySelectorAll('.cmpbtn');
btns.forEach(function(b){b.addEventListener('click',function(){
btns.forEach(function(x){x.classList.toggle('on',x===b);});stage.innerHTML='';note.textContent='';
if(b.dataset.a==='off'){stage.hidden=true;return;}
var a=imgs[b.dataset.a],c=imgs[b.dataset.b];if(!a||!c)return;
var x=document.createElement('img');x.src=a.src;var y=document.createElement('img');y.src=c.src;y.className='top';
stage.appendChild(x);stage.appendChild(y);stage.hidden=false;
var ra=a.naturalWidth/a.naturalHeight,rb=c.naturalWidth/c.naturalHeight;
note.textContent=Math.abs(ra-rb)>0.02?'Black means the same. Bright spots differ. The two images have different sizes, so this is a rough match.':'Black means the same. Bright spots are the differences.';
});});});
var out=document.getElementById('answer');
function answer(){var lines=[];document.querySelectorAll('.screen').forEach(function(sc){
var r=sc.querySelector('input[type=radio]:checked');if(!r||r.value!=='wrong')return;
var w=sc.querySelector('.why').value.trim();lines.push(sc.dataset.unit+': '+sc.dataset.title+(w?': '+w:': needs changes'));});
out.value=lines.length?lines.join('\\n'):'ok';}
document.addEventListener('change',answer);document.addEventListener('input',answer);answer();
document.getElementById('copy').addEventListener('click',function(){out.select();
try{navigator.clipboard.writeText(out.value);}catch(err){document.execCommand('copy');}
this.textContent='Copied';var b=this;setTimeout(function(){b.textContent='Copy answer';},1500);});
"""

ASK = """<section class="ask"><h2>Your answer</h2>
<p>Mark each screen above, then copy this answer and send it in the terminal.</p>
<textarea id="answer" readonly aria-label="Your answer"></textarea><button type="button" id="copy">Copy answer</button>
<ul><li><b>ok</b> means you accept everything as it looks now. A screen marked <i>Differs</i>, <i>Changed, but it must not change</i>
or <i>Not measured</i> then becomes the new normal for that screen.</li>
<li><b>Anything else</b> is a note. It names the part it is about (<code>u4: the title bar sits too low</code>). The run fixes
those parts and sends you a new pack. A note about the whole run, with no screen, you type in the terminal; this box cannot hold it.</li></ul></section>"""


def verdict_banner(total: dict) -> str:
    n, k = total["screens"], total["same"]
    same = ('<p class="hint"><a href="#same">%d screen%s unchanged</a>, folded at the end.</p>' % (k, "" if k == 1 else "s")) if k else ""
    if total["fail"]:
        links = "".join('<li><a href="#%s">%s</a></li>' % (sid, e(t)) for sid, t in total["fail"])
        return ('<div class="banner bad"><b>%d of %d screens differ from the design or changed when they must not.</b> Look at these first:<ul>%s</ul>%s</div>'
                % (len(total["fail"]), n, links, same))
    if total["gap"]:
        return ('<div class="banner"><b>Nothing measured as wrong, but %d of %d screens could not be measured.</b> '
                "Judge those by eye.%s</div>" % (total["gap"], n, same))
    return '<div class="banner good"><b>Nothing measured as wrong.</b> All %d screens match.%s</div>' % (n, same)


def build(pack: str, m: dict) -> tuple[str, dict]:
    os.makedirs(pack, exist_ok=True)
    with open(os.path.join(pack, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("*\n")
    imgs = Images(pack)
    names = m.get("screens") if isinstance(m.get("screens"), dict) else {}
    total = {"fail": [], "gap": 0, "good": 0, "screens": 0}
    parts, nrows, counter, folded = [], 0, [0], []
    for u in m["units"]:
        body, s, f = screens_html(u, imgs, names, counter)
        parts.append(body)
        folded += f
        nrows += len(u["rows"])
        total["fail"] += s["fail"]
        for k in ("gap", "good", "screens"):
            total[k] += s[k]
    total["same"] = len(folded)
    title = m.get("title") or m["slug"]
    head = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>%s · design sign-off</title><style>%s</style></head><body><main>" % (e(title), CSS),
            "<h1>%s</h1>" % e(title),
            "<p>Each screen shows its changed areas first: <b>After</b> (new) next to <b>Design</b> (the goal), or "
            "<b>Before</b> (old) next to <b>After</b> where nothing may change. Then give one answer at the bottom.</p>",
            verdict_banner(total)]
    if str(m.get("note", "")).strip():
        head.append('<p class="note"><b>Your last note</b>: %s</p>' % e(m["note"]))
    tech = ["<details class=\"tech\"><summary>Technical details (PRs, checks, versions)</summary>",
            "<p><code>%s</code> · contract <code>%s</code> · pack %s · built %s · %d units · %d checks</p>" % (
                e(m["slug"]), e(str(m.get("contract", "") or "—")), e(str(m.get("round", 1))),
                e(time.strftime("%Y-%m-%d %H:%M")), len(m["units"]), nrows)]
    prs = [p for p in m.get("prs", []) if isinstance(p, str) and p.strip()]
    if prs:
        tech.append("<ul>%s</ul>" % "".join("<li>%s</li>" % e(p) for p in prs))
    for u in m["units"]:
        checks = [c for c in u.get("checks", []) if isinstance(c, str) and c.strip()]
        if checks:
            tech.append("<h4>%s · how it was checked</h4><ul>%s</ul>" % (
                e(u["unit"]), "".join("<li><code>%s</code></li>" % e(c) for c in checks)))
    tech.append("</details>")
    page = "\n".join(head + parts + [same_html(folded), "\n".join(tech), ASK, "<script>%s</script></main></body></html>" % JS])
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
