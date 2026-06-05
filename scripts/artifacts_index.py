"""Shared artifact index operations with file locking.

Eliminates code duplication between artifact-server.py and deliver-artifact.py.
Uses fcntl.flock for concurrent safety — prevents index.json corruption
when multiple processes register or delete artifacts simultaneously.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACTS_DIR = Path.home() / ".hermes" / "artifacts"
ARTIFACTS_INDEX = ARTIFACTS_DIR / "index.json"
LOCK_FILE = ARTIFACTS_DIR / ".index.lock"

# Maximum versions of the index to retain for rollback
MAX_INDEX_BACKUPS = 3


def _acquire_lock() -> int:
    """Acquire an exclusive lock on the index. Returns the file descriptor."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_lock(fd: int) -> None:
    """Release the lock and close the file descriptor."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _backup_index() -> None:
    """Create a timestamped backup of the current index before mutation."""
    if not ARTIFACTS_INDEX.exists():
        return
    backup_dir = ARTIFACTS_DIR / ".backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_path = backup_dir / f"index.{ts}.json"
    backup_path.write_bytes(ARTIFACTS_INDEX.read_bytes())
    # Prune old backups
    backups = sorted(backup_dir.glob("index.*.json"))
    for old in backups[:-MAX_INDEX_BACKUPS]:
        old.unlink(missing_ok=True)


def load_index() -> dict[str, Any]:
    """Load the artifact index (does NOT acquire lock)."""
    if not ARTIFACTS_INDEX.exists():
        return {"artifacts": []}
    try:
        return json.loads(ARTIFACTS_INDEX.read_text())
    except (json.JSONDecodeError, OSError):
        return {"artifacts": []}


def save_index(data: dict[str, Any], *, _locked: bool = False) -> None:
    """Save the artifact index with locking and backup.

    Set _locked=True if the caller already holds the lock.
    """
    fd: int | None = None
    if not _locked:
        fd = _acquire_lock()
    try:
        if not _locked:
            _backup_index()
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACTS_INDEX.write_text(json.dumps(data, indent=2))
    finally:
        if fd is not None:
            _release_lock(fd)


def register_artifact(
    title: str,
    html_body: str,
    artifact_type: str = "html",
    max_size: int = 1_048_576,  # 1MB default
) -> dict[str, Any]:
    """Register a new artifact. Thread-safe with file locking.

    Raises ValueError if html_body exceeds max_size.
    """
    if len(html_body.encode("utf-8")) > max_size:
        raise ValueError(
            f"HTML body exceeds maximum size of {max_size} bytes "
            f"({len(html_body.encode('utf-8'))} bytes provided)"
        )

    ts = datetime.now(timezone.utc).isoformat()
    aid = hashlib.sha256(f"{ts}{title}".encode()).hexdigest()[:12]
    artifact_path = ARTIFACTS_DIR / f"{aid}.html"
    artifact_path.write_text(html_body, encoding="utf-8")

    fd = _acquire_lock()
    try:
        _backup_index()
        idx = load_index()
        entry: dict[str, Any] = {
            "id": aid,
            "title": title,
            "type": artifact_type,
            "timestamp": ts,
        }
        idx["artifacts"].insert(0, entry)
        idx["artifacts"] = idx["artifacts"][:50]
        save_index(idx, _locked=True)
    finally:
        _release_lock(fd)

    return entry


def list_artifacts() -> list[dict[str, Any]]:
    """List all artifacts with human-readable age strings."""
    idx = load_index()
    now = datetime.now(timezone.utc)
    result: list[dict[str, Any]] = []
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
        except (ValueError, KeyError):
            age = "?"
        result.append({**a, "age": age})
    return result


def get_artifact(aid: str) -> tuple[bytes | None, str]:
    """Retrieve artifact HTML bytes. Returns (data, aid) or (None, aid).

    Handles 'latest' alias and validates path safety.
    """
    if aid == "latest":
        idx = load_index()
        if idx.get("artifacts"):
            aid = idx["artifacts"][0]["id"]
        else:
            return None, aid

    # Sanitize: only allow alphanumeric IDs, prevent path traversal
    if not aid.isalnum():
        return None, aid

    path = (ARTIFACTS_DIR / f"{aid}.html").resolve()
    if not path.is_relative_to(ARTIFACTS_DIR.resolve()):
        return None, aid

    if path.exists():
        return path.read_bytes(), aid
    return None, aid


def latest_age() -> float:
    """Return age in seconds of the most recent artifact, or -1 if none."""
    idx = load_index()
    if not idx.get("artifacts"):
        return -1.0
    try:
        ts = datetime.fromisoformat(idx["artifacts"][0]["timestamp"])
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, KeyError):
        return -1.0


def delete_artifact(aid: str) -> bool:
    """Delete an artifact by ID. Returns True if deleted, False if not found."""
    # Validate ID safety
    if not aid.isalnum():
        return False
    path = (ARTIFACTS_DIR / f"{aid}.html").resolve()
    if not path.is_relative_to(ARTIFACTS_DIR.resolve()):
        return False

    fd = _acquire_lock()
    try:
        _backup_index()
        idx = load_index()
        before = len(idx.get("artifacts", []))
        idx["artifacts"] = [a for a in idx.get("artifacts", []) if a["id"] != aid]
        if len(idx["artifacts"]) == before:
            return False
        save_index(idx, _locked=True)
        if path.exists():
            path.unlink(missing_ok=True)
    finally:
        _release_lock(fd)

    return True


def health_check() -> dict[str, Any]:
    """Return server health status."""
    return {
        "status": "ok",
        "artifacts_dir": str(ARTIFACTS_DIR),
        "artifact_count": len(load_index().get("artifacts", [])),
        "disk_free_mb": _disk_free_mb(ARTIFACTS_DIR),
    }


def _disk_free_mb(path: Path) -> int:
    """Get free disk space in MB for the filesystem containing path."""
    try:
        stat = os.statvfs(path)
        return (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
    except OSError:
        return -1
