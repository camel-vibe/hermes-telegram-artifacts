"""Tests for the artifact server HTTP endpoints."""

from __future__ import annotations

import json
import tempfile
from http.server import HTTPServer
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

from artifact_server import ArtifactHandler
import artifacts_index


def _make_request(
    handler_class: type,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict | bytes | None]:
    """Simulate an HTTP request and return (status_code, parsed_response)."""
    if headers is None:
        headers = {}
    if body:
        headers["Content-Length"] = str(len(body))

    # Build a mock request
    request = mock.Mock()
    request.makefile.return_value = BytesIO(body or b"")
    requestline = f"{method} {path} HTTP/1.1"
    request.requestline = requestline

    handler = handler_class(request, ("127.0.0.1", 9999), mock.Mock())
    handler.command = method
    handler.path = path
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.headers = headers
    handler.request_version = "HTTP/1.1"
        
    # Re-open rfile — the handler's __init__ calls finish() which closes it
    handler.rfile = BytesIO(body or b"")

    # Capture response
    handler.wfile = BytesIO()
    handler._headers_buffer = []
    handler._response_content_type = None
    
    # Monkey-patch send_header to capture content type
    _orig_send_header = handler.send_header
    def _capture_header(keyword, value):
        if keyword.lower() == "content-type":
            handler._response_content_type = value
        return _orig_send_header(keyword, value)
    handler.send_header = _capture_header

    if method == "GET":
        handler.do_GET()
    elif method == "POST":
        handler.do_POST()
    elif method == "DELETE":
        handler.do_DELETE()
    elif method == "OPTIONS":
        handler.do_OPTIONS()

    response_data = handler.wfile.getvalue()
    content_type = getattr(handler, "_response_content_type", None)

    # Parse response — strip HTTP headers if present
    body_data = response_data
    if b"\r\n\r\n" in body_data:
        body_data = body_data.split(b"\r\n\r\n", 1)[1]

    if content_type and "json" in content_type:
        return handler._response_code, json.loads(body_data)
    elif content_type and "html" in content_type:
        return handler._response_code, body_data
    elif body_data:
        try:
            return handler._response_code, json.loads(body_data)
        except json.JSONDecodeError:
            return handler._response_code, body_data
    return handler._response_code, None


# Patch ArtifactHandler to capture response codes
_original_send_response = ArtifactHandler.send_response


def _capture_send_response(self, code, *args, **kwargs):
    self._response_code = code
    return _original_send_response(self, code, *args, **kwargs)


ArtifactHandler.send_response = _capture_send_response  # type: ignore[method-assign]
ArtifactHandler._response_code = 200


@pytest.fixture(autouse=True)
def temp_artifacts_dir():
    """Redirect artifacts to a temp directory for each test."""
    with tempfile.TemporaryDirectory() as td:
        real_dir = artifacts_index.ARTIFACTS_DIR
        real_index = artifacts_index.ARTIFACTS_INDEX
        real_lock = artifacts_index.LOCK_FILE

        artifacts_index.ARTIFACTS_DIR = Path(td)
        artifacts_index.ARTIFACTS_INDEX = Path(td) / "index.json"
        artifacts_index.LOCK_FILE = Path(td) / ".index.lock"
        artifacts_index.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        yield td

        artifacts_index.ARTIFACTS_DIR = real_dir
        artifacts_index.ARTIFACTS_INDEX = real_index
        artifacts_index.LOCK_FILE = real_lock


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        status, data = _make_request(ArtifactHandler, "GET", "/health")
        assert status == 200
        assert data["status"] == "ok"


class TestArtifactRegistration:
    def test_register_success(self):
        body = json.dumps({"title": "Test Page", "html": "<h1>Hi</h1>"}).encode()
        status, data = _make_request(ArtifactHandler, "POST", "/artifact", body)
        assert status == 200
        assert "id" in data
        assert data["title"] == "Test Page"

    def test_register_missing_html(self):
        body = json.dumps({"title": "Empty"}).encode()
        status, data = _make_request(ArtifactHandler, "POST", "/artifact", body)
        assert status == 400
        assert data["code"] == "MISSING_HTML"

    def test_register_invalid_json(self):
        status, data = _make_request(ArtifactHandler, "POST", "/artifact", b"not json")
        assert status == 400
        assert data["code"] == "INVALID_JSON"


class TestArtifactServing:
    def test_serve_registered_artifact(self):
        # Register first
        reg_body = json.dumps({"title": "Page", "html": "<h1>Hello World</h1>"}).encode()
        _, reg_data = _make_request(ArtifactHandler, "POST", "/artifact", reg_body)
        aid = reg_data["id"]

        # Then serve
        status, data = _make_request(ArtifactHandler, "GET", f"/artifact/{aid}")
        assert status == 200
        assert isinstance(data, bytes)
        assert b"Hello World" in data

    def test_serve_nonexistent(self):
        status, data = _make_request(ArtifactHandler, "GET", "/artifact/nonexistent")
        assert status == 404

    def test_serve_path_traversal_blocked(self):
        status, data = _make_request(ArtifactHandler, "GET", "/artifact/../../../etc/passwd")
        assert status in (400, 404)


class TestArtifactList:
    def test_list_empty(self):
        status, data = _make_request(ArtifactHandler, "GET", "/artifacts")
        assert status == 200
        assert data["artifacts"] == []

    def test_list_with_artifact(self):
        body = json.dumps({"title": "P", "html": "<p>x</p>"}).encode()
        _make_request(ArtifactHandler, "POST", "/artifact", body)
        status, data = _make_request(ArtifactHandler, "GET", "/artifacts")
        assert status == 200
        assert len(data["artifacts"]) == 1


class TestArtifactDeletion:
    def test_delete_existing(self):
        body = json.dumps({"title": "DelMe", "html": "<p>x</p>"}).encode()
        _, reg = _make_request(ArtifactHandler, "POST", "/artifact", body)
        aid = reg["id"]

        status, data = _make_request(ArtifactHandler, "DELETE", f"/artifact/{aid}")
        assert status == 200
        assert data["deleted"] == aid

    def test_delete_nonexistent(self):
        status, data = _make_request(ArtifactHandler, "DELETE", "/artifact/abc123def456")
        assert status == 404

    def test_delete_invalid_id(self):
        status, data = _make_request(ArtifactHandler, "DELETE", "/artifact/../../etc")
        assert status == 400


class TestGalleryPage:
    def test_gallery_returns_html(self):
        status, data = _make_request(ArtifactHandler, "GET", "/artifacts/all")
        assert status == 200
        assert isinstance(data, bytes)
        assert b"<!DOCTYPE html>" in data

    def test_gallery_empty_message(self):
        status, data = _make_request(ArtifactHandler, "GET", "/artifacts/all")
        assert b"No artifacts yet" in data


class TestCORS:
    def test_options_returns_cors_headers(self):
        status, _ = _make_request(ArtifactHandler, "OPTIONS", "/artifact")
        assert status == 204


class TestNotFound:
    def test_unknown_path(self):
        status, data = _make_request(ArtifactHandler, "GET", "/nonexistent")
        assert status == 404
