#!/usr/bin/env python3
"""Hermes Artifact Server

Standalone HTTP server that registers, serves, lists, and deletes
Hermes artifacts (interactive HTML widgets for Telegram Mini Apps).

Usage:
    python3 artifact-server.py [--port PORT] [--host HOST]

Defaults: host=127.0.0.1, port=9877

Endpoints:
    POST /artifact          Register {title, html} -> {id, title, timestamp}
    GET  /artifact/<id>     Serve artifact HTML (with TG lifecycle injection)
    GET  /artifact/latest   Serve the most recent artifact
    GET  /artifacts         List all artifacts [{id, title, type, timestamp, age}]
    GET  /artifacts/all     Gallery page (latest expanded, rest collapsed)
    GET  /artifacts/latest-age  Age in seconds of the latest artifact
    DELETE /artifact/<id>   Delete an artifact

Requires: Python 3.10+ (stdlib only, no pip dependencies).
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ARTIFACTS_DIR = Path.home() / ".hermes" / "artifacts"
ARTIFACTS_INDEX = ARTIFACTS_DIR / "index.json"


# ---------------------------------------------------------------------------
# Artifact data operations
# ---------------------------------------------------------------------------

def _load_index():
    if not ARTIFACTS_INDEX.exists():
        return {"artifacts": []}
    try:
        return json.loads(ARTIFACTS_INDEX.read_text())
    except Exception:
        return {"artifacts": []}


def _save_index(data):
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_INDEX.write_text(json.dumps(data, indent=2))


def _register(title, html_body, artifact_type="html"):
    ts = datetime.now(timezone.utc).isoformat()
    aid = hashlib.sha256(f"{ts}{title}".encode()).hexdigest()[:12]
    artifact_path = ARTIFACTS_DIR / f"{aid}.html"
    artifact_path.write_text(html_body, encoding="utf-8")
    idx = _load_index()
    entry = {"id": aid, "title": title, "type": artifact_type, "timestamp": ts}
    idx["artifacts"].insert(0, entry)
    idx["artifacts"] = idx["artifacts"][:50]
    _save_index(idx)
    return entry


def _list():
    idx = _load_index()
    now = datetime.now(timezone.utc)
    result = []
    for a in idx.get("artifacts", []):
        try:
            ts = datetime.fromisoformat(a["timestamp"])
            age_s = (now - ts).total_seconds()
            if age_s < 60:
                age = f"{int(age_s)}s ago"
            elif age_s < 3600:
                age = f"{int(age_s / 60)}m ago"
            elif age_s < 86400:
                age = f"{int(age_s / 3600)}h ago"
            else:
                age = f"{int(age_s / 86400)}d ago"
        except Exception:
            age = "?"
        result.append({**a, "age": age})
    return result


def _serve(aid):
    if aid == "latest":
        idx = _load_index()
        if idx.get("artifacts"):
            aid = idx["artifacts"][0]["id"]
    # Sanitize: only allow alphanumeric IDs, prevent path traversal
    if not aid.isalnum():
        return None, aid
    path = (ARTIFACTS_DIR / f"{aid}.html").resolve()
    if not path.is_relative_to(ARTIFACTS_DIR.resolve()):
        return None, aid
    if path.exists():
        return path.read_bytes(), aid
    return None, aid


def _latest_age():
    idx = _load_index()
    if not idx.get("artifacts"):
        return -1
    try:
        ts = datetime.fromisoformat(idx["artifacts"][0]["timestamp"])
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return -1


def _delete(aid):
    idx = _load_index()
    before = len(idx.get("artifacts", []))
    idx["artifacts"] = [a for a in idx.get("artifacts", []) if a["id"] != aid]
    if len(idx["artifacts"]) == before:
        return False
    _save_index(idx)
    path = ARTIFACTS_DIR / f"{aid}.html"
    if path.exists():
        path.unlink()
    return True


# ---------------------------------------------------------------------------
# TG lifecycle injection script (injected into served HTML)
# ---------------------------------------------------------------------------

def _tg_lifecycle_script():
    """JS that calls tg.ready() and tg.exitFullscreen()."""
    return (
        "<script>"
        "(function(){"
        "var tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;"
        "if(!tg)return;"
        "try{tg.ready();}catch(e){}"
        "try{setTimeout(function(){tg.exitFullscreen();},100);}catch(e){}"
        "})();"
        "</script>"
    )


# ---------------------------------------------------------------------------
# Gallery page HTML (built as list to avoid nested-quote nightmares)
# ---------------------------------------------------------------------------

def _gallery_html():
    """Return the /artifacts/all gallery page. Uses event delegation, no inline onclick."""
    p = []
    p.append('<!DOCTYPE html><html><head>')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append('<style>')
    p.append(':root{--bg:var(--tg-theme-bg-color,#f5f5f5);--card:var(--tg-theme-section-bg-color,#ffffff);--fg:var(--tg-theme-text-color,#1a1a1a);--muted:var(--tg-theme-hint-color,#666);--accent:var(--tg-theme-accent-text-color,#0ea5e9);--border:var(--tg-theme-section-separator-color,#e0e0e0);--green:#16a34a;--red:#dc2626}')
    p.append('*{box-sizing:border-box;margin:0;padding:0}')
    p.append('body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding:16px;min-height:100vh}')
    p.append('.header{font-size:20px;font-weight:600;margin-bottom:16px}')
    p.append('.artifact{background:var(--card);border:0.5px solid var(--border);border-radius:12px;margin-bottom:12px;overflow:hidden}')
    p.append('.artifact-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;user-select:none}')
    p.append('.artifact-header:hover{background:color-mix(in srgb,var(--fg) 4%,transparent)}')
    p.append('.artifact-title{font-size:15px;font-weight:500;flex:1}')
    p.append('.artifact-age{font-size:12px;color:var(--muted);margin-right:12px}')
    p.append('.artifact-actions{display:flex;gap:8px}')
    p.append('.btn{border:none;border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;font-weight:500}')
    p.append('.btn-open{background:var(--green);color:#fff}')
    p.append('.btn-delete{background:transparent;color:var(--red);border:1px solid color-mix(in srgb,var(--red) 20%,transparent)}')
    p.append('.artifact-frame{width:100%;border:none;display:none;background:var(--bg)}')
    p.append('.artifact.open .artifact-frame{display:block}')
    p.append('.arrow{color:var(--muted);transition:transform .15s;margin-right:8px;font-size:12px}')
    p.append('.artifact.open .arrow{transform:rotate(90deg)}')
    p.append('.empty{text-align:center;color:var(--muted);padding:40px 0}')
    p.append('</style></head><body>')
    p.append('<div class="header">Artifacts</div>')
    p.append('<div id="list"></div>')
    p.append('<script>')
    # Fetch artifact list and build cards
    p.append('var base=location.origin;')
    p.append("fetch(base+'/artifacts').then(function(r){return r.json()}).then(function(d){")
    p.append("var list=document.getElementById('list');")
    p.append('var arts=d.artifacts||[];')
    p.append("if(!arts.length){list.innerHTML='<div class=\"empty\">No artifacts yet.</div>';return;}")
    p.append('arts.forEach(function(a,i){')
    p.append("var card=document.createElement('div');")
    p.append("card.className='artifact'+(i===0?' open':'');")
    p.append("card.dataset.id=a.id;")
    # Build header with buttons (no inline onclick — uses data attributes)
    p.append("var hdr=document.createElement('div');hdr.className='artifact-header';")
    p.append("var title=document.createElement('span');title.className='artifact-title';title.textContent=a.title;")
    p.append("var age=document.createElement('span');age.className='artifact-age';age.textContent=a.age;")
    p.append("var acts=document.createElement('div');acts.className='artifact-actions';")
    p.append("var ob=document.createElement('button');ob.className='btn btn-open';ob.textContent='Open';")
    p.append("var db=document.createElement('button');db.className='btn btn-delete';db.textContent='Delete';")
    p.append("acts.appendChild(ob);acts.appendChild(db);")
    p.append("var arrow=document.createElement('span');arrow.className='arrow';arrow.innerHTML='&#9654;';")
    p.append("hdr.appendChild(arrow);hdr.appendChild(title);hdr.appendChild(age);hdr.appendChild(acts);")
    # Build iframe
    p.append("var fr=document.createElement('iframe');fr.className='artifact-frame';fr.src=base+'/artifact/'+a.id;")
    p.append("card.appendChild(hdr);card.appendChild(fr);list.appendChild(card);")
    p.append('});')
    # Auto-resize first iframe
    p.append("var first=list.querySelector('.artifact.open .artifact-frame');")
    p.append("if(first){first.onload=function(){rz(first)};first.style.display='block';}")
    p.append('});')
    # Event delegation — one listener on the list container
    p.append("document.getElementById('list').addEventListener('click',function(e){")
    p.append("var btn=e.target.closest('.btn');")
    p.append("if(btn){e.stopPropagation();")
    p.append("var card=btn.closest('.artifact');var id=card.dataset.id;")
    p.append("if(btn.classList.contains('btn-open')){window.open(base+'/artifact/'+id,'_blank');}")
    p.append("else if(btn.classList.contains('btn-delete')){")
    p.append("var doDelete=function(){fetch(base+'/artifact/'+id,{method:'DELETE'}).then(function(){card.remove();});};")
    p.append("if(window.Telegram&&window.Telegram.WebApp&&window.Telegram.WebApp.showConfirm){")
    p.append("window.Telegram.WebApp.showConfirm('Delete this artifact?',function(ok){if(ok)doDelete();});}")
    p.append("else{if(confirm('Delete this artifact?'))doDelete();}")
    p.append("}")
    p.append("return;}")
    p.append("var hdr=e.target.closest('.artifact-header');")
    p.append("if(hdr){var card=hdr.parentElement;var fr=card.querySelector('.artifact-frame');")
    p.append("if(card.classList.contains('open')){card.classList.remove('open');fr.style.display='none';}")
    p.append("else{card.classList.add('open');fr.style.display='block';fr.onload=function(){rz(fr)};}}")
    p.append('});')
    p.append("function rz(f){try{f.style.height=Math.min(f.contentDocument.body.scrollHeight+4,window.innerHeight*0.85)+'px';}catch(e){}}")
    p.append('var tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;')
    p.append('if(tg){try{tg.ready();tg.setHeaderColor(tg.themeParams?.bg_color||"#f5f5f5");tg.setBackgroundColor(tg.themeParams?.bg_color||"#f5f5f5");tg.onEvent("themeChanged",function(){var p=tg.themeParams;if(p){tg.setHeaderColor(p.bg_color);tg.setBackgroundColor(p.bg_color);}});}catch(e){}}')
    p.append('</script></body></html>')
    return ''.join(p)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ArtifactHandler(BaseHTTPRequestHandler):
    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if self.path == "/artifact":
            try:
                data = json.loads(body)
                title = data.get("title", "Untitled")
                html = data.get("html", "")
                atype = data.get("type", "html")
                if not html:
                    self._respond(400, {"error": "missing html"})
                else:
                    entry = _register(title, html, atype)
                    self._respond(200, entry)
            except Exception as e:
                self._respond(400, {"error": str(e)})
            return

        self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/artifacts":
            self._respond(200, {"artifacts": _list()})
            return

        if self.path == "/artifacts/all":
            html = _gallery_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(html.encode())
            return

        if self.path == "/artifacts/latest-age":
            self._respond(200, {"age": _latest_age()})
            return

        if self.path.startswith("/artifact/"):
            aid = self.path[len("/artifact/"):]
            data, aid = _serve(aid)
            if data:
                # Inject TG lifecycle script before </body>
                script = _tg_lifecycle_script()
                if b"</body>" in data:
                    data = data.replace(b"</body>", script.encode() + b"</body>", 1)
                else:
                    data += script.encode()

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(data)
            else:
                self._respond(404, {"error": "artifact not found"})
            return

        self._respond(404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/artifact/"):
            aid = self.path[len("/artifact/"):]
            # Sanitize: only allow alphanumeric IDs
            if not aid.isalnum():
                self._respond(400, {"error": "invalid artifact id"})
                return
            if _delete(aid):
                self._respond(200, {"deleted": aid})
            else:
                self._respond(404, {"error": "artifact not found"})
            return

        self._respond(404, {"error": "not found"})

    def log_message(self, format, *args):
        sys.stderr.write(f"[artifact-server] {args[0]}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hermes Artifact Server")
    parser.add_argument("--port", type=int, default=9877, help="Port (default: 9877)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer((args.host, args.port), ArtifactHandler)
    print(f"[artifact-server] Listening on {args.host}:{args.port}", flush=True)
    print(f"[artifact-server] Artifacts dir: {ARTIFACTS_DIR}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[artifact-server] Shutting down.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
