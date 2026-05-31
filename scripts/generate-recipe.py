#!/usr/bin/env python3
"""
Generate a recipe artifact from the template.

Usage:
  # From JSON data file:
  python3 generate-recipe.py --data recipe.json

  # Quick inline:
  python3 generate-recipe.py --title "Stir-fry chicken" --servings 4 \
    --ingredients "Chicken thigh,500,g|Soy sauce,3,tbsp|Ginger,1,piece" \
    --steps "Cut chicken into pieces|Marinate 15 min|Stir-fry in hot wok"

JSON format:
{
  "title": "Stir-fry chicken",
  "servings": 4,
  "prepTime": "15 min",
  "cookTime": "20 min",
  "totalTime": "35 min",
  "difficulty": "Easy",
  "sections": [
    {
      "name": "Ingredients",
      "items": [
        {"name": "Chicken thigh", "amount": 500, "unit": "g"},
        {"name": "Soy sauce", "amount": 3, "unit": "tbsp"},
        {"name": "Ginger", "amount": 1, "unit": "piece", "note": "sliced thin"}
      ]
    }
  ],
  "steps": [
    {"text": "Cut chicken into bite-sized pieces", "timer": 0},
    {"text": "Marinate with soy sauce and ginger", "timer": 900},
    {"text": "Stir-fry in hot wok until golden", "timer": 480}
  ],
  "notes": ["Substitute thigh with breast for lighter version"]
}

Steps with "timer" in seconds show a countdown button. Set timer to 0 or omit for no timer.
"""

import json
import re
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "recipe.html"


def build_sections_js(sections):
    lines = []
    for section in sections:
        lines.append("    {")
        lines.append("      name: " + json.dumps(section["name"]) + ",")
        lines.append("      items: [")
        for item in section["items"]:
            parts = []
            parts.append("        { name: " + json.dumps(item["name"]))
            if "amount" in item and item["amount"] is not None:
                parts.append(", amount: " + str(item["amount"]))
            if "unit" in item and item["unit"]:
                parts.append(", unit: " + json.dumps(item["unit"]))
            if "note" in item and item["note"]:
                parts.append(", note: " + json.dumps(item["note"]))
            parts.append(" },")
            lines.append("".join(parts))
        lines.append("      ]")
        lines.append("    },")
    return "\n".join(lines)


def build_steps_js(steps):
    lines = []
    for step in steps:
        timer = step.get("timer", 0)
        if timer:
            lines.append('    { text: ' + json.dumps(step["text"]) + ', timer: ' + str(timer) + ' },')
        else:
            lines.append('    { text: ' + json.dumps(step["text"]) + ' },')
    return "\n".join(lines)


def build_notes_js(notes):
    return ", ".join(json.dumps(n) for n in notes)


def generate(data, storage_key=None):
    title = data.get("title", "Recipe")
    servings = data.get("servings", 4)
    prep_time = data.get("prepTime", "")
    cook_time = data.get("cookTime", "")
    total_time = data.get("totalTime", "")
    difficulty = data.get("difficulty", "")
    sections = data.get("sections", [])
    steps = data.get("steps", [])
    notes = data.get("notes", [])

    if not storage_key:
        storage_key = "recipe_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")

    with open(TEMPLATE_PATH, "r") as f:
        template = f.read()

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{SERVINGS}}", str(servings))
    html = html.replace("{{PREP_TIME}}", prep_time)
    html = html.replace("{{COOK_TIME}}", cook_time)
    html = html.replace("{{TOTAL_TIME}}", total_time)
    html = html.replace("{{DIFFICULTY}}", difficulty)
    html = html.replace("{{STORAGE_KEY}}", storage_key)
    html = html.replace("{{SECTIONS_JSON}}", build_sections_js(sections))
    html = html.replace("{{STEPS_JSON}}", build_steps_js(steps))
    html = html.replace("{{NOTES_JSON}}", build_notes_js(notes))

    out_path = Path("/tmp") / f"recipe-{storage_key}.html"
    with open(out_path, "w") as f:
        f.write(html)

    return str(out_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a recipe artifact")
    parser.add_argument("--data", help="JSON file with recipe data")
    parser.add_argument("--title", help="Recipe title (for inline mode)")
    parser.add_argument("--servings", type=int, default=4)
    parser.add_argument("--prep-time", default="")
    parser.add_argument("--cook-time", default="")
    parser.add_argument("--total-time", default="")
    parser.add_argument("--difficulty", default="")
    parser.add_argument("--ingredients", help="Pipe-separated: name,amount,unit|name,amount,unit")
    parser.add_argument("--steps", help="Pipe-separated steps: step1|step2|step3")
    parser.add_argument("--timers", help="Comma-separated timer durations in seconds (parallel to steps)")
    parser.add_argument("--notes", help="Pipe-separated notes")
    parser.add_argument("--storage-key", help="localStorage key")
    args = parser.parse_args()

    if args.data:
        with open(args.data) as f:
            data = json.load(f)
    elif args.title:
        data = {
            "title": args.title,
            "servings": args.servings,
            "prepTime": args.prep_time,
            "cookTime": args.cook_time,
            "totalTime": args.total_time,
            "difficulty": args.difficulty,
            "sections": [],
            "steps": [],
            "notes": [],
        }
        if args.ingredients:
            items = []
            for part in args.ingredients.split("|"):
                fields = [f.strip() for f in part.split(",")]
                item = {"name": fields[0]}
                if len(fields) > 1 and fields[1]:
                    item["amount"] = float(fields[1])
                if len(fields) > 2 and fields[2]:
                    item["unit"] = fields[2]
                if len(fields) > 3 and fields[3]:
                    item["note"] = fields[3]
                items.append(item)
            data["sections"] = [{"name": "Ingredients", "items": items}]

        if args.steps:
            step_texts = [s.strip() for s in args.steps.split("|")]
            timers = []
            if args.timers:
                timers = [int(t.strip()) for t in args.timers.split(",")]
            data["steps"] = []
            for i, text in enumerate(step_texts):
                step = {"text": text}
                if i < len(timers) and timers[i] > 0:
                    step["timer"] = timers[i]
                data["steps"].append(step)

        if args.notes:
            data["notes"] = [n.strip() for n in args.notes.split("|")]
    else:
        print("Provide --data or --title")
        sys.exit(1)

    out = generate(data, args.storage_key)
    print(f"Generated: {out}")
    print(f"Sections: {len(data.get('sections', []))}, Steps: {len(data.get('steps', []))}")
