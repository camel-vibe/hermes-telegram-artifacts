#!/usr/bin/env python3
"""Hermes Artifact Server

Standalone HTTP server that registers, serves, lists, and deletes
Hermes artifacts (interactive HTML widgets for Telegram Mini Apps).

Usage:
    python3 artifact_server.py [--port PORT] [--host HOST]

Defaults: host=127.0.0.1, port=9877

Endpoints:
    GET  /health              Health check with artifact count and disk space
    POST /artifact            Register {title, html} -> {id, title, timestamp}
    GET  /artifact/<id>       Serve artifact HTML (with TG lifecycle injection)
    GET  /artifact/latest     Serve the most recent artifact
    GET  /artifacts           List all artifacts [{id, title, type, timestamp, age}]
    GET  /artifacts/all       Gallery page (latest expanded, rest collapsed)
    GET  /artifacts/latest-age  Age in seconds of the latest artifact
    DELETE /artifact/<id>     Delete an artifact

Requires: Python 3.10+ (stdlib only, no pip dependencies).
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

# Shared index module (stdlib, same directory)
from artifacts_index import (
    ARTIFACTS_DIR,
    DEFAULT_MAX_SIZE,
    ArtifactTooLargeError,
    delete_artifact,
    get_artifact,
    health_check,
    latest_age,
    list_artifacts,
    register_artifact,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [artifact-server] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("artifact-server")

# Hard ceiling on a request body. Generous over DEFAULT_MAX_SIZE to allow for
# JSON wrapping/escaping; register_artifact enforces the real per-artifact limit.
MAX_REQUEST_BYTES = DEFAULT_MAX_SIZE * 4

# ---------------------------------------------------------------------------
# TG lifecycle injection script
# ---------------------------------------------------------------------------


def _tg_lifecycle_script() -> str:
    """JS that initializes the Telegram Mini App WebView."""
    return (
        "<script>"
        "(function(){"
        "var tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;"
        "if(!tg)return;"
        "try{tg.ready();}catch(e){console.error('[artifact-server] tg.ready failed:',e);}"
        "try{setTimeout(function(){tg.exitFullscreen();},100);}catch(e){console.error('[artifact-server] exitFullscreen failed:',e);}"
        "})();"
        "</script>"
    )


# ---------------------------------------------------------------------------
# Gallery page HTML
# ---------------------------------------------------------------------------


def _gallery_html() -> str:
    """Return the /artifacts/all gallery page. Uses event delegation."""
    p: list[str] = []
    p.append('<!DOCTYPE html><html><head>')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append("<style>")
    p.append(":root{--bg:var(--tg-theme-bg-color,#f5f5f5);--card:var(--tg-theme-section-bg-color,#ffffff);--fg:var(--tg-theme-text-color,#1a1a1a);--muted:var(--tg-theme-hint-color,#666);--accent:var(--tg-theme-accent-text-color,#0ea5e9);--border:var(--tg-theme-section-separator-color,#e0e0e0);--green:#16a34a;--red:#dc2626}")
    p.append("*{box-sizing:border-box;margin:0;padding:0}")
    p.append("body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding:16px;min-height:100vh}")
    p.append(".header{font-size:20px;font-weight:600;margin-bottom:16px}")
    p.append(".artifact{background:var(--card);border:0.5px solid var(--border);border-radius:12px;margin-bottom:12px;overflow:hidden}")
    p.append(".artifact-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;user-select:none}")
    p.append(".artifact-header:hover{background:color-mix(in srgb,var(--fg) 4%,transparent)}")
    p.append(".artifact-title{font-size:15px;font-weight:500;flex:1}")
    p.append(".artifact-age{font-size:12px;color:var(--muted);margin-right:12px}")
    p.append(".artifact-actions{display:flex;gap:8px}")
    p.append(".btn{border:none;border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;font-weight:500}")
    p.append(".btn-open{background:var(--green);color:#fff}")
    p.append(".btn-delete{background:transparent;color:var(--red);border:1px solid color-mix(in srgb,var(--red) 20%,transparent)}")
    p.append(".artifact-frame{width:100%;border:none;display:none;background:var(--bg)}")
    p.append(".artifact.open .artifact-frame{display:block}")
    p.append(".arrow{color:var(--muted);transition:transform .15s;margin-right:8px;font-size:12px}")
    p.append(".artifact.open .arrow{transform:rotate(90deg)}")
    p.append(".empty{text-align:center;color:var(--muted);padding:40px 0}")
    p.append("</style></head><body>")
    p.append('<div class="header">Artifacts</div>')
    p.append('<div id="list"></div>')
    p.append("<script>")
    p.append("var base=location.origin;")
    p.append("fetch(base+'/artifacts').then(function(r){return r.json()}).then(function(d){")
    p.append("var list=document.getElementById('list');")
    p.append("var arts=d.artifacts||[];")
    p.append("if(!arts.length){list.innerHTML='<div class=\"empty\">No artifacts yet.</div>';return;}")
    p.append("arts.forEach(function(a,i){")
    p.append("var card=document.createElement('div');")
    p.append("card.className='artifact'+(i===0?' open':'');")
    p.append("card.dataset.id=a.id;")
    p.append("var hdr=document.createElement('div');hdr.className='artifact-header';")
    p.append("var title=document.createElement('span');title.className='artifact-title';title.textContent=a.title;")
    p.append("var age=document.createElement('span');age.className='artifact-age';age.textContent=a.age;")
    p.append("var acts=document.createElement('div');acts.className='artifact-actions';")
    p.append("var ob=document.createElement('button');ob.className='btn btn-open';ob.textContent='Open';")
    p.append("var db=document.createElement('button');db.className='btn btn-delete';db.textContent='Delete';")
    p.append("acts.appendChild(ob);acts.appendChild(db);")
    p.append("var arrow=document.createElement('span');arrow.className='arrow';arrow.innerHTML='&#9654;';")
    p.append("hdr.appendChild(arrow);hdr.appendChild(title);hdr.appendChild(age);hdr.appendChild(acts);")
    p.append("var fr=document.createElement('iframe');fr.className='artifact-frame';fr.src=base+'/artifact/'+a.id;")
    p.append("card.appendChild(hdr);card.appendChild(fr);list.appendChild(card);")
    p.append("});")
    p.append("var first=list.querySelector('.artifact.open .artifact-frame');")
    p.append("if(first){first.onload=function(){rz(first)};first.style.display='block';}")
    p.append("});")
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
    p.append("});")
    p.append("function rz(f){try{f.style.height=Math.min(f.contentDocument.body.scrollHeight+4,window.innerHeight*0.85)+'px';}catch(e){}}")
    p.append("var tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;")
    p.append('if(tg){try{tg.ready();tg.setHeaderColor(tg.themeParams?.bg_color||"#f5f5f5");tg.setBackgroundColor(tg.themeParams?.bg_color||"#f5f5f5");tg.onEvent("themeChanged",function(){var p=tg.themeParams;if(p){tg.setHeaderColor(p.bg_color);tg.setBackgroundColor(p.bg_color);}});}catch(e){console.error("[gallery] TG init failed:",e);}}')
    p.append("</script></body></html>")
    return "".join(p)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class ArtifactHandler(BaseHTTPRequestHandler):
    """HTTP request handler for artifact server."""

    # HTTP/1.1 enables keep-alive; every bodied response sends Content-Length.
    protocol_version = "HTTP/1.1"

    # Silence per-request logging from BaseHTTPRequestHandler (route to DEBUG).
    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)

    @staticmethod
    def _route(path: str) -> str:
        """Strip any query string / fragment, returning just the path."""
        return path.split("?", 1)[0].split("#", 1)[0]

    def _write_body(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        cache: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if not cache:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _respond(self, status: int, data: dict[str, Any]) -> None:
        # JSON endpoints are dynamic (listings, health, ages); never cache them,
        # so the gallery's fetch('/artifacts') doesn't show a stale list.
        body = json.dumps(data).encode("utf-8")
        self._write_body(status, body, "application/json", cache=False)

    def _error(self, status: int, message: str, code: str = "ERROR") -> None:
        self._respond(status, {"error": message, "code": code})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        try:
            if self._route(self.path) != "/artifact":
                self._error(404, "not found", "NOT_FOUND")
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                self._error(400, "invalid Content-Length", "BAD_REQUEST")
                return
            if length < 0:
                self._error(400, "invalid Content-Length", "BAD_REQUEST")
                return
            if length > MAX_REQUEST_BYTES:
                self._error(413, "request body too large", "PAYLOAD_TOO_LARGE")
                return

            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._error(400, "invalid JSON body", "INVALID_JSON")
                return
            if not isinstance(data, dict):
                self._error(400, "JSON body must be an object", "INVALID_JSON")
                return

            title = str(data.get("title", "Untitled"))
            html = str(data.get("html", ""))
            atype = str(data.get("type", "html"))

            if not html.strip():
                self._error(400, "missing html content", "MISSING_HTML")
                return

            try:
                entry = register_artifact(title, html, atype)
            except ArtifactTooLargeError as e:
                self._error(413, str(e), "PAYLOAD_TOO_LARGE")
                return

            log.info("Registered artifact %s: %s", entry["id"], title)
            self._respond(200, entry)
        except BrokenPipeError:
            log.warning("client disconnected during POST")
        except Exception:
            log.exception("Failed to handle POST")
            self._safe_500()

    def do_HEAD(self) -> None:
        # Same routing as GET; _write_body suppresses the body for HEAD.
        self.do_GET()

    def do_GET(self) -> None:
        path = self._route(self.path)
        try:
            if path == "/health":
                self._respond(200, health_check())
                return

            if path == "/artifacts":
                self._respond(200, {"artifacts": list_artifacts()})
                return

            if path == "/artifacts/all":
                self._write_body(
                    200, _gallery_html().encode("utf-8"),
                    "text/html; charset=utf-8", cache=False,
                )
                return

            if path == "/artifacts/latest-age":
                self._respond(200, {"age": latest_age()})
                return

            if path.startswith("/artifact/"):
                aid = path[len("/artifact/"):]
                data, _ = get_artifact(aid)
                if data is None:
                    self._error(404, "artifact not found", "NOT_FOUND")
                    return
                script = _tg_lifecycle_script().encode("utf-8")
                if b"</body>" in data:
                    data = data.replace(b"</body>", script + b"</body>", 1)
                else:
                    data = data + script
                self._write_body(200, data, "text/html; charset=utf-8", cache=False)
                return

            self._error(404, "not found", "NOT_FOUND")
        except BrokenPipeError:
            log.warning("client disconnected during GET %s", path)
        except Exception:
            log.exception("Failed to handle GET %s", path)
            self._safe_500()

    def do_DELETE(self) -> None:
        path = self._route(self.path)
        try:
            if not path.startswith("/artifact/"):
                self._error(404, "not found", "NOT_FOUND")
                return

            aid = path[len("/artifact/"):]
            if not aid.isalnum():
                self._error(400, "invalid artifact id", "INVALID_ID")
                return

            if delete_artifact(aid):
                log.info("Deleted artifact %s", aid)
                self._respond(200, {"deleted": aid})
            else:
                self._error(404, "artifact not found", "NOT_FOUND")
        except BrokenPipeError:
            log.warning("client disconnected during DELETE %s", path)
        except Exception:
            log.exception("Failed to handle DELETE %s", path)
            self._safe_500()

    def _safe_500(self) -> None:
        """Best-effort 500. Swallows errors if the response already started."""
        try:
            self._error(500, "internal server error", "INTERNAL_ERROR")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Artifact Server")
    parser.add_argument("--port", type=int, default=9877, help="Port (default: 9877)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # ThreadingHTTPServer (stdlib) handles each request in its own daemon thread,
    # so concurrent requests (e.g. a gallery loading many iframes) don't serialize.
    server = ThreadingHTTPServer((args.host, args.port), ArtifactHandler)

    def shutdown_handler(signum: int, frame: Any) -> None:
        log.info("Received signal %s, shutting down gracefully...", signum)
        # shutdown() blocks until serve_forever() returns and must run off the
        # main thread (serve_forever is running there).
        Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    log.info("Listening on %s:%s", args.host, args.port)
    log.info("Artifacts dir: %s", ARTIFACTS_DIR)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Server shut down.")
        server.server_close()


if __name__ == "__main__":
    main()
