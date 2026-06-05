#!/usr/bin/env python3
"""Register an artifact with the Hermes artifact server over HTTP.

Usage: python3 register-artifact.py <html_file> "Title Here"
   or: echo '<html>...</html>' | python3 register-artifact.py - "Title Here"

POSTs the HTML to the running artifact server (http://127.0.0.1:9877), which
stores it under ~/.hermes/artifacts/ and adds it to the index. The server must
already be running (start it with: python3 scripts/artifact-server.py).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SERVER_URL = "http://127.0.0.1:9877/artifact"


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: register-artifact.py <html_file|-> "Title"')
        print("  Use - for stdin")
        sys.exit(1)

    html_path = sys.argv[1]
    title = sys.argv[2]

    if html_path == "-":
        html = sys.stdin.read()
    else:
        source = Path(html_path)
        if not source.is_file():
            print(f"Failed: file not found: {html_path}", file=sys.stderr)
            sys.exit(1)
        html = source.read_text(encoding="utf-8")

    data = json.dumps({"title": title, "html": html}).encode("utf-8")
    req = urllib.request.Request(
        SERVER_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        print(f"Registered: {result['id']} — {title}")
    except urllib.error.URLError as e:
        print(
            f"Failed: could not reach artifact server at {SERVER_URL} ({e.reason}). "
            "Is it running? Start it with: python3 scripts/artifact-server.py",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
