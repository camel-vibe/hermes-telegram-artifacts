"""Tests for the shared artifacts_index module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Point the module at a temp directory
import artifacts_index


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

        # Create the directory
        artifacts_index.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        yield td

        artifacts_index.ARTIFACTS_DIR = real_dir
        artifacts_index.ARTIFACTS_INDEX = real_index
        artifacts_index.LOCK_FILE = real_lock


class TestLoadSaveIndex:
    def test_load_empty_index(self):
        result = artifacts_index.load_index()
        assert result == {"artifacts": []}

    def test_save_and_load_index(self):
        data = {"artifacts": [{"id": "abc123", "title": "Test"}]}
        artifacts_index.save_index(data)
        loaded = artifacts_index.load_index()
        assert loaded == data

    def test_load_corrupt_index_returns_empty(self, temp_artifacts_dir):
        artifacts_index.ARTIFACTS_INDEX.write_text("not valid json {{{")
        result = artifacts_index.load_index()
        assert result == {"artifacts": []}


class TestRegisterArtifact:
    def test_register_basic(self):
        entry = artifacts_index.register_artifact("Test", "<html></html>")
        assert entry["title"] == "Test"
        assert entry["type"] == "html"
        assert len(entry["id"]) == 12
        assert "timestamp" in entry

    def test_register_creates_file(self, temp_artifacts_dir):
        entry = artifacts_index.register_artifact("My Page", "<h1>Hi</h1>")
        path = artifacts_index.ARTIFACTS_DIR / f"{entry['id']}.html"
        assert path.exists()
        assert path.read_text() == "<h1>Hi</h1>"

    def test_register_appears_in_index(self, temp_artifacts_dir):
        artifacts_index.register_artifact("First", "<p>1</p>")
        idx = artifacts_index.load_index()
        assert len(idx["artifacts"]) == 1
        assert idx["artifacts"][0]["title"] == "First"

    def test_register_size_limit(self):
        with pytest.raises(ValueError, match="exceeds maximum size"):
            artifacts_index.register_artifact("Big", "x" * 2_000_000, max_size=1024)

    def test_register_respects_max_50(self, temp_artifacts_dir):
        for i in range(60):
            artifacts_index.register_artifact(f"Artifact {i}", f"<p>{i}</p>")
        idx = artifacts_index.load_index()
        assert len(idx["artifacts"]) == 50
        # Most recent should be first
        assert idx["artifacts"][0]["title"] == "Artifact 59"


class TestGetArtifact:
    def test_get_existing(self, temp_artifacts_dir):
        entry = artifacts_index.register_artifact("Page", "<h1>Hello</h1>")
        data, aid = artifacts_index.get_artifact(entry["id"])
        assert data is not None
        assert b"<h1>Hello</h1>" in data
        assert aid == entry["id"]

    def test_get_nonexistent(self):
        data, aid = artifacts_index.get_artifact("nonexistent")
        assert data is None

    def test_get_latest(self, temp_artifacts_dir):
        artifacts_index.register_artifact("Old", "<p>old</p>")
        entry = artifacts_index.register_artifact("New", "<p>new</p>")
        data, aid = artifacts_index.get_artifact("latest")
        assert data is not None
        assert b"<p>new</p>" in data
        assert aid == entry["id"]

    def test_get_latest_empty(self, temp_artifacts_dir):
        data, aid = artifacts_index.get_artifact("latest")
        assert data is None

    def test_path_traversal_blocked(self, temp_artifacts_dir):
        # Attempt to escape the artifacts directory
        data, _ = artifacts_index.get_artifact("../etc/passwd")
        assert data is None

    def test_non_alnum_id_blocked(self, temp_artifacts_dir):
        data, _ = artifacts_index.get_artifact("abc/def")
        assert data is None


class TestListArtifacts:
    def test_list_includes_age(self, temp_artifacts_dir):
        artifacts_index.register_artifact("Page", "<p>x</p>")
        result = artifacts_index.list_artifacts()
        assert len(result) == 1
        assert "age" in result[0]
        assert result[0]["title"] == "Page"


class TestDeleteArtifact:
    def test_delete_existing(self, temp_artifacts_dir):
        entry = artifacts_index.register_artifact("ToDelete", "<p>x</p>")
        assert artifacts_index.delete_artifact(entry["id"]) is True
        data, _ = artifacts_index.get_artifact(entry["id"])
        assert data is None

    def test_delete_nonexistent(self):
        assert artifacts_index.delete_artifact("nonexistent") is False

    def test_delete_removes_from_index(self, temp_artifacts_dir):
        entry = artifacts_index.register_artifact("X", "<p>x</p>")
        artifacts_index.delete_artifact(entry["id"])
        idx = artifacts_index.load_index()
        assert all(a["id"] != entry["id"] for a in idx["artifacts"])

    def test_delete_path_traversal_blocked(self, temp_artifacts_dir):
        assert artifacts_index.delete_artifact("../etc/passwd") is False


class TestLatestAge:
    def test_latest_age_empty(self):
        assert artifacts_index.latest_age() == -1.0

    def test_latest_age_positive(self, temp_artifacts_dir):
        artifacts_index.register_artifact("Page", "<p>x</p>")
        age = artifacts_index.latest_age()
        assert age >= 0


class TestHealthCheck:
    def test_health_check(self, temp_artifacts_dir):
        artifacts_index.register_artifact("Page", "<p>x</p>")
        result = artifacts_index.health_check()
        assert result["status"] == "ok"
        assert result["artifact_count"] == 1
        assert "disk_free_mb" in result
