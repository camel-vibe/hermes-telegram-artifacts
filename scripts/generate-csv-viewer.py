#!/usr/bin/env python3
"""Generate a CSV viewer artifact from a CSV file or inline data.

Usage:
  # From a CSV file:
  python3 generate-csv-viewer.py --file data.csv --title "Employee data"

  # Inline CSV string:
  python3 generate-csv-viewer.py --csv "Name,Score\nAlice,95\nBob,87"

  # From stdin:
  cat data.csv | python3 generate-csv-viewer.py --stdin --title "Scores"

Output: writes to /tmp/csv-viewer-<slug>.html, prints the path.
"""
import argparse
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).parent.parent / "templates" / "csv-viewer.html"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def main():
    p = argparse.ArgumentParser(description="Generate CSV viewer artifact")
    p.add_argument("--file", "-f", help="Path to CSV file")
    p.add_argument("--csv", "-c", help="Inline CSV string")
    p.add_argument("--stdin", action="store_true", help="Read CSV from stdin")
    p.add_argument("--title", "-t", default="CSV data", help="Viewer title")
    p.add_argument("--out", "-o", help="Output path (default: /tmp/csv-viewer-<slug>.html)")
    args = p.parse_args()

    # Read CSV data
    if args.file:
        csv_data = Path(args.file).read_text()
    elif args.stdin:
        csv_data = sys.stdin.read()
    elif args.csv:
        csv_data = args.csv
    else:
        p.error("Provide --file, --csv, or --stdin")

    # Escape backticks and ${} for JS template literal
    csv_escaped = csv_data.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    # Fill template
    html = TEMPLATE.read_text()
    html = html.replace("{{TITLE}}", args.title)
    html = html.replace("{{CSV_DATA}}", csv_escaped)

    # Write output
    out_path = args.out or f"/tmp/csv-viewer-{slugify(args.title)}.html"
    Path(out_path).write_text(html)
    print(out_path)


if __name__ == "__main__":
    main()
