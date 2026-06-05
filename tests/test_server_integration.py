"""End-to-end tests against a real running artifact server.

These exercise the actual ThreadingHTTPServer + ArtifactHandler over real HTTP
sockets (the unit tests mock the request/response plumbing), and verify
concurrency safety of the file-locked index under simultaneous registrations.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import artifacts_index
from artifact_server import ArtifactHandler


@pytest.fixture
def server():
    """Start a real server on an ephemeral port with a temp artifacts dir."""
    with tempfile.TemporaryDirectory() as td:
        saved = (
            artifacts_index.ARTIFACTS_DIR,
            artifacts_index.ARTIFACTS_INDEX,
            artifacts_index.LOCK_FILE,
        )
        artifacts_index.ARTIFACTS_DIR = Path(td)
        artifacts_index.ARTIFACTS_INDEX = Path(td) / "index.json"
        artifacts_index.LOCK_FILE = Path(td) / ".index.lock"

        srv = ThreadingHTTPServer(("127.0.0.1", 0), ArtifactHandler)
        host, port = srv.server_address[0], srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield {"base": f"http://{host}:{port}", "host": host, "port": port}
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)
            (
                artifacts_index.ARTIFACTS_DIR,
                artifacts_index.ARTIFACTS_INDEX,
                artifacts_index.LOCK_FILE,
            ) = saved


def _request(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            parsed = json.loads(raw) if "json" in ctype else raw
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


class TestEndToEnd:
    def test_health(self, server):
        status, data = _request(server["base"], "GET", "/health")
        assert status == 200
        assert data["status"] == "ok"

    def test_register_serve_list_delete(self, server):
        base = server["base"]
        status, reg = _request(base, "POST", "/artifact", {"title": "T", "html": "<h1>Hi</h1>"})
        assert status == 200
        aid = reg["id"]

        status, body = _request(base, "GET", f"/artifact/{aid}")
        assert status == 200
        assert b"Hi" in body
        # Lifecycle script is injected on serve.
        assert b"Telegram" in body

        status, listing = _request(base, "GET", "/artifacts")
        assert status == 200
        assert len(listing["artifacts"]) == 1

        status, latest = _request(base, "GET", "/artifact/latest")
        assert status == 200
        assert b"Hi" in latest

        status, deleted = _request(base, "DELETE", f"/artifact/{aid}")
        assert status == 200
        assert deleted["deleted"] == aid

        status, _ = _request(base, "GET", f"/artifact/{aid}")
        assert status == 404

    def test_gallery_page(self, server):
        status, body = _request(server["base"], "GET", "/artifacts/all")
        assert status == 200
        assert b"<!DOCTYPE html>" in body

    def test_latest_age(self, server):
        _request(server["base"], "POST", "/artifact", {"title": "T", "html": "<p>x</p>"})
        status, data = _request(server["base"], "GET", "/artifacts/latest-age")
        assert status == 200
        assert data["age"] >= 0

    def test_unknown_path_404(self, server):
        status, _ = _request(server["base"], "GET", "/nope")
        assert status == 404

    def test_invalid_json_400(self, server):
        base = server["base"]
        req = urllib.request.Request(
            base + "/artifact", data=b"not json", method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

    def test_missing_html_400(self, server):
        status, data = _request(server["base"], "POST", "/artifact", {"title": "x"})
        assert status == 400
        assert data["code"] == "MISSING_HTML"

    def test_payload_too_large_413(self, server):
        big = "x" * (artifacts_index.DEFAULT_MAX_SIZE + 1024)
        status, data = _request(server["base"], "POST", "/artifact", {"title": "B", "html": big})
        assert status == 413
        assert data["code"] == "PAYLOAD_TOO_LARGE"

    def test_query_string_is_ignored(self, server):
        base = server["base"]
        _, reg = _request(base, "POST", "/artifact", {"title": "Q", "html": "<p>q</p>"})
        status, body = _request(base, "GET", f"/artifact/{reg['id']}?v=123")
        assert status == 200
        assert b"q" in body

    def test_path_traversal_blocked_raw_socket(self, server):
        # urllib normalises '..' away, so use a raw socket to send it verbatim.
        status = _raw_get(server["host"], server["port"], "/artifact/../../../etc/passwd")
        assert status in (400, 404)

    def test_concurrent_registration_is_lock_safe(self, server):
        # Without correct file locking, simultaneous index updates would lose
        # entries. All N must survive with distinct ids.
        base = server["base"]
        n = 30

        def reg(i):
            status, data = _request(base, "POST", "/artifact", {"title": f"C{i}", "html": f"<p>{i}</p>"})
            assert status == 200
            return data["id"]

        with ThreadPoolExecutor(max_workers=12) as pool:
            ids = list(pool.map(reg, range(n)))

        status, listing = _request(base, "GET", "/artifacts")
        assert status == 200
        assert len(listing["artifacts"]) == n
        assert len(set(ids)) == n


def _raw_get(host, port, raw_path):
    """Send a GET with an un-normalised path and return the status code."""
    conn = socket.create_connection((host, port), timeout=5)
    try:
        conn.sendall(
            f"GET {raw_path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
        )
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        conn.close()
    # Status line: "HTTP/1.1 404 Not Found"
    return int(data.split(b" ", 2)[1])
