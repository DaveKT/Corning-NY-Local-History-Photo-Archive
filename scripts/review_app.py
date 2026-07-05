#!/usr/bin/env python3
"""
Stage D of the description-refinement pipeline: human review app.

A small local web app (standard library only) for working through the human
review queue produced by scripts/adjudicate_photos.py. For each flagged photo
it shows the image, the current record, and the proposed record side by side.

Keyboard shortcuts:
    a = accept proposed record
    k = keep original record
    e = edit fields before saving
    arrows = previous / next photo

Decisions are appended to data/refinement/review_decisions.json immediately
after every verdict, so a session can be stopped and resumed at any time.
Accepted changes are also appended to data/refinement/corrections.json in the
overlay format consumed by scripts/apply_corrections.py.

Usage:
    python scripts/review_app.py [--queue data/refinement/human_queue.json]
    # then open http://localhost:8765
"""

import argparse
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = REPO_ROOT / "data" / "refinement" / "human_queue.json"
DEFAULT_PHOTOS_DIR = REPO_ROOT / "data" / "photos"
DEFAULT_DECISIONS = REPO_ROOT / "data" / "refinement" / "review_decisions.json"
DEFAULT_CORRECTIONS = REPO_ROOT / "data" / "refinement" / "corrections.json"

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Photo record review</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0;
        background: #f5f5f4; color: #1c1917; }}
 .top {{ padding: 10px 18px; background: #292524; color: #fafaf9;
        display: flex; justify-content: space-between; align-items: center; }}
 .top b {{ font-size: 15px; }}
 .wrap {{ display: flex; gap: 18px; padding: 18px; align-items: flex-start; }}
 .photo {{ flex: 1.1; text-align: center; }}
 .photo img {{ max-width: 100%; max-height: 78vh; border: 1px solid #d6d3d1;
              background: #fff; }}
 .panel {{ flex: 1; }}
 .meta {{ color: #57534e; font-size: 13px; margin-bottom: 10px; }}
 table {{ width: 100%; border-collapse: collapse; background: #fff;
         font-size: 13.5px; }}
 th, td {{ border: 1px solid #e7e5e4; padding: 7px 9px; text-align: left;
          vertical-align: top; }}
 th {{ background: #fafaf9; width: 90px; }}
 td.changed {{ background: #fef9c3; }}
 .why {{ background: #eef2ff; border: 1px solid #c7d2fe; padding: 8px 10px;
        font-size: 13px; margin: 10px 0; border-radius: 6px; }}
 .btns {{ margin-top: 14px; display: flex; gap: 10px; }}
 button {{ font-size: 14px; padding: 9px 16px; border-radius: 7px;
          border: 1px solid #a8a29e; background: #fff; cursor: pointer; }}
 button.accept {{ background: #16a34a; color: #fff; border-color: #15803d; }}
 button.keep {{ background: #f5f5f4; }}
 button.edit {{ background: #f59e0b; color: #fff; border-color: #d97706; }}
 button:hover {{ filter: brightness(0.95); }}
 kbd {{ background: #e7e5e4; border-radius: 3px; padding: 0 5px;
       font-size: 11px; }}
 #editor {{ display: none; margin-top: 12px; }}
 #editor textarea, #editor select {{ width: 100%; font-size: 13px;
    font-family: inherit; margin: 2px 0 8px; box-sizing: border-box; }}
 .done {{ padding: 60px; text-align: center; font-size: 20px; }}
</style></head>
<body>
<div class="top">
  <b>Photo record review</b>
  <span id="progress"></span>
</div>
<div id="app"></div>
<script>
const CATEGORIES = {categories_json};
let queue = [], decided = {{}}, idx = 0;

async function load() {{
  const r = await fetch('/state'); const s = await r.json();
  queue = s.queue; decided = s.decided;
  idx = queue.findIndex(q => !(q.LHNo in decided));
  if (idx < 0) idx = 0;
  render();
}}
function esc(t) {{ const d = document.createElement('div');
  d.textContent = t ?? ''; return d.innerHTML; }}
function row(label, oldv, newv) {{
  const changed = (newv ?? oldv) !== oldv;
  return `<tr><th>${{label}}</th><td>${{esc(oldv)}}</td>` +
         `<td class="${{changed ? 'changed' : ''}}">${{esc(newv ?? oldv)}}</td></tr>`;
}}
function proposed(item, field) {{
  const adj = item.adjudication;
  if (adj) return adj['final_' + field];
  return item['proposed_' + field.replace('tags','tags')
                    .replace('description','description')] ?? null;
}}
function render() {{
  const nDone = Object.keys(decided).length;
  document.getElementById('progress').textContent =
     `${{nDone}} / ${{queue.length}} reviewed`;
  const app = document.getElementById('app');
  if (!queue.length || nDone >= queue.length) {{
    app.innerHTML = '<div class="done">All photos reviewed 🎉<br>' +
      '<small>Decisions saved. You can close this window.</small></div>';
    return;
  }}
  if (idx >= queue.length) idx = queue.length - 1;
  const item = queue[idx];
  const pt = proposed(item, 'tags') ?? item.proposed_tags;
  const pd = proposed(item, 'description') ?? item.proposed_description;
  const pc = proposed(item, 'category') ?? item.proposed_category;
  const already = item.LHNo in decided
      ? `<div class="why">Already decided: <b>${{decided[item.LHNo]}}</b>
         (deciding again overwrites)</div>` : '';
  app.innerHTML = `
  <div class="wrap">
    <div class="photo"><img src="/photo/${{item.filename}}"></div>
    <div class="panel">
      <h3 style="margin:0 0 4px">${{item.LHNo}}
        <small>(#${{idx + 1}} of ${{queue.length}})</small></h3>
      <div class="meta">Subject: <b>${{esc(item.subject) || '—'}}</b>
        &nbsp; Date: <b>${{esc(item.date) || '—'}}</b><br>
        Flags: ${{esc((item.reasons || []).join(', '))}}</div>
      ${{already}}
      <div class="why"><b>Why review:</b> ${{esc(item.human_reason || '')}}
        ${{item.adjudication ? '<br><b>Adjudicator:</b> ' +
           esc(item.adjudication.rationale) : ''}}</div>
      <table>
        <tr><th></th><th>Current</th><th>Proposed</th></tr>
        ${{row('Tags', item.baseline_tags, pt)}}
        ${{row('Description', item.baseline_description, pd)}}
        ${{row('Category', item.baseline_category, pc)}}
      </table>
      <div class="btns">
        <button class="accept" onclick="decide('accept')">
          Accept proposed <kbd>a</kbd></button>
        <button class="keep" onclick="decide('keep')">
          Keep original <kbd>k</kbd></button>
        <button class="edit" onclick="toggleEdit()">
          Edit… <kbd>e</kbd></button>
        <button onclick="move(-1)">&larr;</button>
        <button onclick="move(1)">&rarr;</button>
      </div>
      <div id="editor">
        <label>Tags</label><textarea id="etags" rows="2"></textarea>
        <label>Description</label><textarea id="edesc" rows="4"></textarea>
        <label>Category</label><select id="ecat"></select><br>
        <button class="accept" onclick="decide('edit')">Save edited</button>
      </div>
    </div>
  </div>`;
  const sel = document.getElementById('ecat');
  for (const c of CATEGORIES) {{
    const o = document.createElement('option'); o.textContent = c;
    if (c === (pc || item.baseline_category)) o.selected = true;
    sel.appendChild(o);
  }}
  document.getElementById('etags').value = pt ?? item.baseline_tags ?? '';
  document.getElementById('edesc').value = pd ?? item.baseline_description ?? '';
}}
function toggleEdit() {{
  const e = document.getElementById('editor');
  e.style.display = e.style.display === 'block' ? 'none' : 'block';
}}
function move(d) {{ idx = Math.min(Math.max(idx + d, 0), queue.length - 1);
  render(); }}
async function decide(verdict) {{
  const item = queue[idx];
  const body = {{ lh: item.LHNo, verdict }};
  if (verdict === 'edit') {{
    body.tags = document.getElementById('etags').value;
    body.description = document.getElementById('edesc').value;
    body.category = document.getElementById('ecat').value;
  }}
  await fetch('/decide', {{ method: 'POST', body: JSON.stringify(body) }});
  decided[item.LHNo] = verdict;
  let next = queue.findIndex((q, i) => i > idx && !(q.LHNo in decided));
  if (next < 0) next = queue.findIndex(q => !(q.LHNo in decided));
  idx = next < 0 ? idx : next;
  render();
}}
document.addEventListener('keydown', ev => {{
  if (ev.target.tagName === 'TEXTAREA' || ev.target.tagName === 'SELECT')
    return;
  if (ev.key === 'a') decide('accept');
  else if (ev.key === 'k') decide('keep');
  else if (ev.key === 'e') toggleEdit();
  else if (ev.key === 'ArrowLeft') move(-1);
  else if (ev.key === 'ArrowRight') move(1);
}});
load();
</script>
</body></html>
"""

VALID_CATEGORIES = [
    "Disasters & Floods", "Military & War", "Archaeological Artifacts",
    "Glass & Decorative Arts", "Industry & Manufacturing",
    "Sports & Recreation", "Commerce & Business", "Civic Life & Events",
    "Education", "People & Portraits", "Transportation",
    "Domestic & Family Life", "Streetscapes & Architecture",
    "Landscapes & Natural Features",
]


class ReviewState:
    def __init__(self, queue_path: Path, photos_dir: Path,
                 decisions_path: Path, corrections_path: Path):
        self.photos_dir = photos_dir
        self.decisions_path = decisions_path
        self.corrections_path = corrections_path

        raw = json.loads(queue_path.read_text())
        self.queue = []
        for lh in sorted(raw):
            entry = dict(raw[lh])
            entry["LHNo"] = lh
            self.queue.append(entry)
        self.by_lh = {e["LHNo"]: e for e in self.queue}

        self.decisions = {}
        if decisions_path.exists():
            self.decisions = json.loads(decisions_path.read_text())
        self.corrections = []
        if corrections_path.exists():
            self.corrections = json.loads(corrections_path.read_text())

    def final_value(self, entry: dict, field: str):
        adj = entry.get("adjudication")
        if adj and adj.get(f"final_{field}"):
            return adj[f"final_{field}"]
        return entry.get(f"proposed_{field}")

    def decide(self, lh: str, verdict: str, edited: dict) -> None:
        entry = self.by_lh[lh]
        finals = {}
        if verdict == "keep":
            pass  # no corrections
        else:
            for field in ("tags", "description", "category"):
                if verdict == "edit":
                    finals[field] = edited.get(field)
                else:
                    finals[field] = self.final_value(entry, field)

        # Replace any previous corrections for this photo (re-decision).
        self.corrections = [c for c in self.corrections
                            if not (c["lh"] == lh and c["source"] == "human")]
        for field, new in finals.items():
            old = entry.get(f"baseline_{field}")
            if new and new != old:
                self.corrections.append({
                    "lh": lh, "field": field, "old": old, "new": new,
                    "source": "human", "verdict": verdict,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })

        self.decisions[lh] = verdict
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.decisions_path.write_text(json.dumps(self.decisions, indent=2))
        self.corrections_path.write_text(
            json.dumps(self.corrections, indent=2))


def make_handler(state: ReviewState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, content: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/index"):
                page = PAGE.format(
                    categories_json=json.dumps(VALID_CATEGORIES))
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif self.path == "/state":
                body = json.dumps({"queue": state.queue,
                                   "decided": state.decisions})
                self._send(200, body.encode(), "application/json")
            elif self.path.startswith("/photo/"):
                name = Path(self.path[len("/photo/"):]).name
                fp = state.photos_dir / name
                if fp.exists():
                    self._send(200, fp.read_bytes(), "image/jpeg")
                else:
                    self._send(404, b"not found", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path == "/decide":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                state.decide(body["lh"], body["verdict"], body)
                self._send(200, b"{}", "application/json")
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Human review web app.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--photos-dir", default=str(DEFAULT_PHOTOS_DIR))
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS))
    parser.add_argument("--corrections", default=str(DEFAULT_CORRECTIONS))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    state = ReviewState(Path(args.queue), Path(args.photos_dir),
                        Path(args.decisions), Path(args.corrections))
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(state))
    url = f"http://localhost:{args.port}"
    print(f"Review app: {url}  ({len(state.queue)} photos in queue, "
          f"{len(state.decisions)} already decided)")
    print("Ctrl-C to stop. Decisions are saved after every verdict.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
