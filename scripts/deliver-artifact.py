#!/usr/bin/env python3
"""Save an artifact HTML file and register it in the index.

Usage:
  python3 deliver-artifact.py <artifact_id> <html_file>
  python3 deliver-artifact.py <artifact_id> -          # read from stdin

This script saves the file and updates the index so the artifact server
can list it. Uses the shared artifacts_index module with file locking.
"""

from __future__ import annotations

import sys
from pathlib import Path

from artifacts_index import ARTIFACTS_DIR, register_artifact


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    artifact_id: str = sys.argv[1]
    html_path: str = sys.argv[2]

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Read HTML
    if html_path == "-":
        html = sys.stdin.read()
    else:
        source = Path(html_path)
        if not source.is_file():
            print(f"ERROR: file not found: {html_path}", file=sys.stderr)
            sys.exit(1)
        html = source.read_text(encoding="utf-8")

    # Write to the artifact path with the given ID
    out = ARTIFACTS_DIR / f"{artifact_id}.html"
    out.write_text(html, encoding="utf-8")

    # Register via shared module (thread-safe with file locking)
    try:
        entry = register_artifact(artifact_id, html)
        print(f"OK id={entry['id']} path={out}")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
