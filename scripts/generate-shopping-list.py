#!/usr/bin/env python3
"""
Generate a shopping list artifact from the template.

Usage:
  # Interactive prompt:
  python3 generate-shopping-list.py

  # From JSON file:
  python3 generate-shopping-list.py --data items.json --title "Weekly groceries"

  # From inline items:
  python3 generate-shopping-list.py --title "BBQ stuff" --items "Charcoal,Burgers,Ketchup"

JSON format:
[
  {"name": "Milk"},
  {"name": "Green long pepper", "note": "pointed pepper / 长青椒"}
]
"""

import json
import os
import re
import sys

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "shopping-list.html")


def build_items_js(items):
    """Convert item list to JS array literal for embedding in template."""
    lines = []
    for item in items:
        if "note" in item and item["note"]:
            lines.append(f"  {{ name: '{item['name'].replace(chr(39), chr(39)+chr(92)+chr(39))}', note: '{item['note'].replace(chr(39), chr(39)+chr(92)+chr(39))}' }},")
        else:
            lines.append(f"  {{ name: '{item['name'].replace(chr(39), chr(39)+chr(92)+chr(39))}' }},")
    return "\n" + "\n".join(lines) + "\n"


def generate(title, items, storage_key=None):
    with open(TEMPLATE_PATH, "r") as f:
        template = f.read()

    if not storage_key:
        storage_key = "shopping_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")

    items_js = build_items_js(items)

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{STORAGE_KEY}}", storage_key)
    html = html.replace("{{DEFAULT_ITEMS_JS}}", items_js)

    out_path = os.path.join("/tmp", f"shopping-{storage_key}.html")
    with open(out_path, "w") as f:
        f.write(html)

    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a shopping list artifact")
    parser.add_argument("--title", default="Shopping list")
    parser.add_argument("--items", help="Comma-separated item names")
    parser.add_argument("--data", help="JSON file with items [{name, note?}]")
    parser.add_argument("--storage-key", help="localStorage key (auto-derived from title)")
    parser.add_argument("--out", help="Output path (default: /tmp/shopping-<key>.html)")
    args = parser.parse_args()

    if args.data:
        with open(args.data) as f:
            items = json.load(f)
    elif args.items:
        items = [{"name": n.strip()} for n in args.items.split(",") if n.strip()]
    else:
        # Interactive
        print("Enter items (one per line, empty line to finish):")
        items = []
        while True:
            try:
                line = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            items.append({"name": line})
        if not items:
            print("No items. Exiting.")
            sys.exit(1)

    out = generate(args.title, items, args.storage_key)
    if args.out:
        os.rename(out, args.out)
        out = args.out

    print(f"Generated: {out}")
    print(f"Items: {len(items)}")
