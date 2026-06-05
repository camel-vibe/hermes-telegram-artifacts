#!/usr/bin/env python3
"""Generate a markdown viewer artifact.

Usage:
  python3 generate-markdown-viewer.py --file notes.md --title "Meeting notes"
  echo "# Hello" | python3 generate-markdown-viewer.py --stdin --title "Quick note"
  python3 generate-markdown-viewer.py --md "# Title\nSome text" --title "Inline"
"""
import argparse
import re
import sys
from pathlib import Path

from artifact_escape import esc_html, js_template

TEMPLATE = Path(__file__).parent.parent / "templates" / "markdown-viewer.html"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def main():
    p = argparse.ArgumentParser(description="Generate markdown viewer artifact")
    p.add_argument("--file", "-f", help="Path to markdown file")
    p.add_argument("--md", "-m", help="Inline markdown string")
    p.add_argument("--stdin", action="store_true", help="Read markdown from stdin")
    p.add_argument("--title", "-t", default="Document", help="Viewer title")
    p.add_argument("--out", "-o", help="Output path (default: /tmp/markdown-viewer-<slug>.html)")
    args = p.parse_args()

    if args.file:
        md_data = Path(args.file).read_text(encoding="utf-8")
    elif args.stdin:
        md_data = sys.stdin.read()
    elif args.md:
        md_data = args.md
    else:
        p.error("Provide --file, --md, or --stdin")

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("{{TITLE}}", esc_html(args.title))
    html = html.replace("{{MARKDOWN_DATA}}", js_template(md_data))

    out_path = args.out or f"/tmp/markdown-viewer-{slugify(args.title)}.html"
    Path(out_path).write_text(html, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
