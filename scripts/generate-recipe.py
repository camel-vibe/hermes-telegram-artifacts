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

from artifact_escape import js_json, js_number, js_str

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "recipe.html"


def build_sections_js(sections):
    lines = []
    for section in sections:
        lines.append("    {")
        lines.append("      name: " + js_json(section["name"]) + ",")
        lines.append("      items: [")
        for item in section["items"]:
            parts = []
            parts.append("        { name: " + js_json(item["name"]))
            amount = item.get("amount")
            if amount is not None and amount != "":
                # The template multiplies amount by the scale factor, so it must
                # be a bare numeric literal. js_number coerces non-numeric input
                # to 0, which the template renders as "no amount".
                parts.append(", amount: " + js_number(amount))
            if item.get("unit"):
                parts.append(", unit: " + js_json(item["unit"]))
            if item.get("note"):
                parts.append(", note: " + js_json(item["note"]))
            parts.append(" },")
            lines.append("".join(parts))
        lines.append("      ]")
        lines.append("    },")
    return "\n".join(lines)


def build_steps_js(steps):
    lines = []
    for step in steps:
        timer = step.get("timer", 0)
        try:
            timer_secs = int(float(timer))
        except (TypeError, ValueError):
            timer_secs = 0
        if timer_secs > 0:
            lines.append("    { text: " + js_json(step["text"]) + ", timer: " + str(timer_secs) + " },")
        else:
            lines.append("    { text: " + js_json(step["text"]) + " },")
    return "\n".join(lines)


def build_notes_js(notes):
    return ", ".join(js_json(n) for n in notes)


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

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # Title/time/difficulty go into single-quoted JS strings; servings into a
    # bare numeric literal (the template scales it); storage_key is [a-z0-9_].
    html = template.replace("{{TITLE}}", js_str(title))
    html = html.replace("{{SERVINGS}}", js_number(servings, default="4"))
    html = html.replace("{{PREP_TIME}}", js_str(prep_time))
    html = html.replace("{{COOK_TIME}}", js_str(cook_time))
    html = html.replace("{{TOTAL_TIME}}", js_str(total_time))
    html = html.replace("{{DIFFICULTY}}", js_str(difficulty))
    html = html.replace("{{STORAGE_KEY}}", storage_key)
    html = html.replace("{{SECTIONS_JSON}}", build_sections_js(sections))
    html = html.replace("{{STEPS_JSON}}", build_steps_js(steps))
    html = html.replace("{{NOTES_JSON}}", build_notes_js(notes))

    out_path = Path("/tmp") / f"recipe-{storage_key}.html"
    with open(out_path, "w", encoding="utf-8") as f:
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
        with open(args.data, encoding="utf-8") as f:
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
