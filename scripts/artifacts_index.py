"""Shared artifact index operations with file locking.

Eliminates code duplication between artifact_server.py and deliver-artifact.py.
Uses fcntl.flock for concurrent safety — prevents index.json corruption
when multiple processes register or delete artifacts simultaneously.

Index writes are atomic (write-to-temp + os.replace) so a crash mid-write
can never leave a truncated index, and concurrent readers never observe a
partial file.
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

# Maximum number of artifacts retained in the index. Older entries (and their
# HTML files) are pruned beyond this.
MAX_ARTIFACTS = 50

# Default ceiling on a single artifact's HTML body.
DEFAULT_MAX_SIZE = 1_048_576  # 1 MB

# Maximum versions of the index to retain for rollback
MAX_INDEX_BACKUPS = 3


class ArtifactTooLargeError(ValueError):
    """Raised when an artifact's HTML body exceeds the configured size limit."""


def _acquire_lock() -> int:
    """Acquire an exclusive lock on the index. Returns the file descriptor."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
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


def _safe_artifact_path(aid: str) -> Path | None:
    """Resolve the on-disk path for an artifact id, or None if the id is unsafe.

    Only alphanumeric ids are permitted, and the resolved path must stay
    inside ARTIFACTS_DIR (defence in depth against path traversal).
    """
    if not aid or not aid.isalnum():
        return None
    base = ARTIFACTS_DIR.resolve()
    path = (ARTIFACTS_DIR / f"{aid}.html").resolve()
    if not path.is_relative_to(base):
        return None
    return path


def _backup_index() -> None:
    """Create a timestamped backup of the current index before mutation."""
    if not ARTIFACTS_INDEX.exists():
        return
    backup_dir = ARTIFACTS_DIR / ".backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    # Microsecond precision so rapid successive mutations don't clobber backups.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    backup_path = backup_dir / f"index.{ts}.json"
    try:
        backup_path.write_bytes(ARTIFACTS_INDEX.read_bytes())
    except OSError:
        return
    # Prune old backups, keeping the most recent MAX_INDEX_BACKUPS.
    backups = sorted(backup_dir.glob("index.*.json"))
    for old in backups[:-MAX_INDEX_BACKUPS]:
        old.unlink(missing_ok=True)


def load_index() -> dict[str, Any]:
    """Load the artifact index (does NOT acquire lock)."""
    if not ARTIFACTS_INDEX.exists():
        return {"artifacts": []}
    try:
        data = json.loads(ARTIFACTS_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {"artifacts": []}
    # Guard against a structurally-valid-but-wrong-shape file.
    if not isinstance(data, dict) or not isinstance(data.get("artifacts"), list):
        return {"artifacts": []}
    return data


def save_index(data: dict[str, Any], *, _locked: bool = False) -> None:
    """Save the artifact index atomically, with locking and backup.

    Set _locked=True if the caller already holds the lock.
    """
    fd: int | None = None
    if not _locked:
        fd = _acquire_lock()
    try:
        if not _locked:
            _backup_index()
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ARTIFACTS_INDEX.with_name(ARTIFACTS_INDEX.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, ARTIFACTS_INDEX)  # atomic on the same filesystem
    finally:
        if fd is not None:
            _release_lock(fd)


def register_artifact(
    title: str,
    html_body: str,
    artifact_type: str = "html",
    max_size: int = DEFAULT_MAX_SIZE,
    *,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Register a new artifact. Thread-safe and process-safe via file locking.

    If artifact_id is given it is used verbatim (it must be alphanumeric);
    otherwise a content-addressed id is generated. Re-registering an existing
    id replaces the entry and moves it to the front.

    Raises ArtifactTooLargeError if html_body exceeds max_size.
    Raises ValueError if artifact_id is provided but not alphanumeric.
    """
    encoded_len = len(html_body.encode("utf-8"))
    if encoded_len > max_size:
        raise ArtifactTooLargeError(
            f"HTML body exceeds maximum size of {max_size} bytes "
            f"({encoded_len} bytes provided)"
        )

    ts = datetime.now(timezone.utc).isoformat()
    if artifact_id is not None:
        if not artifact_id.isalnum():
            raise ValueError(f"artifact_id must be alphanumeric, got {artifact_id!r}")
        aid = artifact_id
    else:
        aid = hashlib.sha256(f"{ts}{title}".encode()).hexdigest()[:12]

    path = _safe_artifact_path(aid)
    if path is None:  # pragma: no cover - aid is validated above
        raise ValueError(f"invalid artifact id: {aid!r}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(html_body, encoding="utf-8")

    entry: dict[str, Any] = {
        "id": aid,
        "title": title,
        "type": artifact_type,
        "timestamp": ts,
    }

    fd = _acquire_lock()
    try:
        _backup_index()
        idx = load_index()
        # De-duplicate: drop any existing entry with this id, then prepend.
        artifacts = [a for a in idx.get("artifacts", []) if a.get("id") != aid]
        artifacts.insert(0, entry)
        dropped = artifacts[MAX_ARTIFACTS:]
        idx["artifacts"] = artifacts[:MAX_ARTIFACTS]
        save_index(idx, _locked=True)
    finally:
        _release_lock(fd)

    # Remove HTML files for entries pushed out of the index so the artifacts
    # directory doesn't grow without bound.
    for old in dropped:
        old_path = _safe_artifact_path(old.get("id", ""))
        if old_path is not None and old_path != path:
            old_path.unlink(missing_ok=True)

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
        except (ValueError, KeyError, TypeError):
            age = "?"
        result.append({**a, "age": age})
    return result


def get_artifact(aid: str) -> tuple[bytes | None, str]:
    """Retrieve artifact HTML bytes. Returns (data, aid) or (None, aid).

    Handles the 'latest' alias and validates path safety.
    """
    if aid == "latest":
        idx = load_index()
        artifacts = idx.get("artifacts")
        if artifacts:
            aid = artifacts[0]["id"]
        else:
            return None, aid

    path = _safe_artifact_path(aid)
    if path is None:
        return None, aid

    try:
        return path.read_bytes(), aid
    except (FileNotFoundError, IsADirectoryError):
        return None, aid


def latest_age() -> float:
    """Return age in seconds of the most recent artifact, or -1 if none."""
    idx = load_index()
    artifacts = idx.get("artifacts")
    if not artifacts:
        return -1.0
    try:
        ts = datetime.fromisoformat(artifacts[0]["timestamp"])
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, KeyError, TypeError):
        return -1.0


def delete_artifact(aid: str) -> bool:
    """Delete an artifact by ID. Returns True if deleted, False if not found."""
    path = _safe_artifact_path(aid)
    if path is None:
        return False

    fd = _acquire_lock()
    try:
        _backup_index()
        idx = load_index()
        artifacts = idx.get("artifacts", [])
        remaining = [a for a in artifacts if a.get("id") != aid]
        if len(remaining) == len(artifacts):
            return False
        idx["artifacts"] = remaining
        save_index(idx, _locked=True)
    finally:
        _release_lock(fd)

    path.unlink(missing_ok=True)
    return True


def _disk_free_mb(path: Path) -> int:
    """Get free disk space in MB for the filesystem containing path."""
    try:
        stat = os.statvfs(path)
        return (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
    except OSError:
        return -1


def health_check() -> dict[str, Any]:
    """Return server health status."""
    return {
        "status": "ok",
        "artifacts_dir": str(ARTIFACTS_DIR),
        "artifact_count": len(load_index().get("artifacts", [])),
        "disk_free_mb": _disk_free_mb(ARTIFACTS_DIR),
    }
