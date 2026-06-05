#!/usr/bin/env python3
"""Save an artifact HTML file and register it in the index.

Usage:
  python3 deliver-artifact.py <artifact_id> <html_file> [title]
  python3 deliver-artifact.py <artifact_id> -            # read from stdin

Saves the HTML under the GIVEN artifact id and updates the index so the
artifact server can list and serve it. The id must be alphanumeric (the same
ids the server generates). Uses the shared artifacts_index module, which
writes the file and updates the index atomically under a file lock.

No Telegram API call is made — this only writes to ~/.hermes/artifacts/.
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
    title: str = sys.argv[3] if len(sys.argv) > 3 else artifact_id

    # Read HTML
    if html_path == "-":
        html = sys.stdin.read()
    else:
        source = Path(html_path)
        if not source.is_file():
            print(f"ERROR: file not found: {html_path}", file=sys.stderr)
            sys.exit(1)
        html = source.read_text(encoding="utf-8")

    # Register under the requested id. register_artifact writes the file and
    # the index entry atomically; passing artifact_id keeps the id stable.
    try:
        entry = register_artifact(title, html, artifact_id=artifact_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    out = ARTIFACTS_DIR / f"{entry['id']}.html"
    print(f"OK id={entry['id']} path={out}")


if __name__ == "__main__":
    main()
