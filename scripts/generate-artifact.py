#!/usr/bin/env python3
"""Generate artifact HTML from structured JSON data.

Usage:
  python3 generate-artifact.py --type itinerary < data.json > out.html
  python3 generate-artifact.py --type report --data data.json --out out.html
  python3 generate-artifact.py --list  # show supported types and their schemas

Supported types: itinerary, report, comparison, reference

Then register with:
  python3 register-artifact.py out.html "Title"
"""
import json, sys, argparse

# ─── Theme + boilerplate ───
HEAD = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:var(--tg-theme-bg-color,#f5f5f5);--card:var(--tg-theme-section-bg-color,#ffffff);--fg:var(--tg-theme-text-color,#1a1a1a);--muted:var(--tg-theme-hint-color,#666);--cyan:var(--tg-theme-accent-text-color,#0ea5e9);--green:#16a34a;--red:#dc2626;--yellow:#d97706;--border:var(--tg-theme-section-separator-color,#e0e0e0);--input-bg:color-mix(in srgb,var(--fg) 5%,transparent)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:16px;line-height:1.5}
.card{background:var(--card);border:0.5px solid var(--border);border-radius:12px;padding:14px;margin-bottom:10px}
.section-title{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px;padding-bottom:6px;border-bottom:0.5px solid var(--border)}
.line{display:flex;justify-content:space-between;align-items:baseline;padding:5px 0;font-size:13px}
.line+.line{border-top:0.5px solid var(--border)}
.line-label{color:var(--fg);flex:1}
.line-note{color:var(--muted);font-size:11px;margin-left:6px}
.line-value{font-family:'SF Mono',monospace;font-weight:500;text-align:right;white-space:nowrap;margin-left:12px}
.val-green{color:var(--green)}.val-red{color:var(--red)}.val-bold{font-weight:600;color:var(--fg)}.val-primary{color:var(--cyan)}
.subtotal{background:rgba(14,165,233,.06);border-radius:8px;padding:10px 12px;margin:8px 0}
.subtotal .line{font-size:14px}.subtotal .line-label{font-weight:500}
.result-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px}
.result-item{text-align:center;padding:10px 0}
.result-label{font-size:10px;color:var(--muted);margin-bottom:2px;text-transform:uppercase;letter-spacing:.03em}
.result-num{font-size:18px;font-weight:600;font-family:'SF Mono',monospace}
.result-num.primary{color:var(--cyan)}.result-num.positive{color:var(--green)}.result-num.negative{color:var(--red)}
.tag{display:inline-block;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:500;margin-left:6px}
.tag-blue{background:rgba(14,165,233,.12);color:var(--cyan)}
.tag-green{background:rgba(22,163,74,.12);color:var(--green)}
.tag-red{background:rgba(220,38,38,.12);color:var(--red)}
.tag-yellow{background:rgba(217,119,6,.12);color:var(--yellow)}
</style>
</head>
<body>"""

TAIL = """<script>
const tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;
if(tg){try{tg.ready();tg.setHeaderColor(tg.themeParams?.bg_color||'#f5f5f5');tg.setBackgroundColor(tg.themeParams?.bg_color||'#f5f5f5');tg.onEvent('themeChanged',function(){var p=tg.themeParams;if(p){tg.setHeaderColor(p.bg_color);tg.setBackgroundColor(p.bg_color);}});}catch(e){console.error('[TG]',e);}}
</script>
</body>
</html>"""

# ─── Tag helper ───
TAG_COLORS = {"blue":"tag-blue","green":"tag-green","red":"tag-red","yellow":"tag-yellow"}
def tag(text, color="blue"):
    c = TAG_COLORS.get(color, "tag-blue")
    return f'<span class="tag {c}">{esc(text)}</span>'

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

# ─── Itinerary generator ───
def gen_itinerary(data):
    """data = {title, subtitle?, summary?: [{label, value, note?}], days: [{date, label?, events: [{time, title, note?, tag?, tag_color?}]}]}
    """
    parts = []
    # Header
    title = esc(data.get("title","Itinerary"))
    subtitle = data.get("subtitle","")
    parts.append(f'<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    # Summary row
    summary = data.get("summary", [])
    if summary:
        parts.append('<div class="result-grid">')
        for s in summary:
            n = "primary"
            parts.append(f'<div class="result-item"><div class="result-label">{esc(s["label"])}</div><div class="result-num {n}">{esc(s["value"])}</div></div>')
        parts.append('</div>')

    # Days
    for day in data.get("days", []):
        day_label = day.get("label", "")
        day_date = esc(day.get("date",""))
        header = f"Day {day_date}" + (f" — {esc(day_label)}" if day_label else "")
        parts.append('<div class="card">')
        parts.append(f'<div class="section-title">{header}</div>')
        for ev in day.get("events", []):
            time_str = esc(ev.get("time",""))
            title_str = esc(ev.get("title",""))
            note_str = ev.get("note","")
            tag_text = ev.get("tag","")
            tag_color = ev.get("tag_color","blue")
            value_str = esc(ev.get("value",""))

            # Label shows time + the event title (previously the title was
            # computed but dropped, so itinerary events rendered without names).
            label_html = " ".join(b for b in (time_str, title_str) if b)
            if note_str:
                label_html += f' <span class="line-note">{esc(note_str)}</span>'

            value_html = value_str
            if tag_text:
                value_html += tag(tag_text, tag_color)

            parts.append(f'<div class="line"><span class="line-label">{label_html}</span><span class="line-value">{value_html}</span></div>')
        parts.append('</div>')

    return "\n".join(parts)

# ─── Report generator ───
def gen_report(data):
    """data = {title, subtitle?, sections: [{title?, lines: [{label, value, note?, color?}], subtotal?: {label, value}}]}
    """
    parts = []
    title = esc(data.get("title","Report"))
    subtitle = data.get("subtitle","")
    parts.append('<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    for sec in data.get("sections", []):
        parts.append('<div class="card">')
        sec_title = sec.get("title","")
        if sec_title:
            parts.append(f'<div class="section-title">{esc(sec_title)}</div>')
        for ln in sec.get("lines", []):
            color = ln.get("color","")
            val_cls = f"val-{color}" if color else ""
            note = ln.get("note","")
            note_html = f'<span class="line-note">{esc(note)}</span>' if note else ""
            parts.append(f'<div class="line"><span class="line-label">{esc(ln["label"])} {note_html}</span><span class="line-value {val_cls}">{esc(ln["value"])}</span></div>')
        st = sec.get("subtotal")
        if st:
            parts.append('<div class="subtotal">')
            parts.append(f'<div class="line"><span class="line-label">{esc(st["label"])}</span><span class="line-value val-primary">{esc(st["value"])}</span></div>')
            parts.append('</div>')
        parts.append('</div>')

    return "\n".join(parts)

# ─── Comparison generator ───
def gen_comparison(data):
    """data = {title, items: [{name, fields: [{label, value, color?}]}]}
    """
    parts = []
    title = esc(data.get("title","Comparison"))
    parts.append(f'<div class="card"><div style="font-size:16px;font-weight:600">{title}</div></div>')

    items = data.get("items",[])
    cols = min(len(items), 3)
    parts.append(f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:10px">')
    for item in items:
        parts.append('<div class="card" style="margin-bottom:0">')
        parts.append(f'<div style="font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;margin-bottom:8px">{esc(item["name"])}</div>')
        for f in item.get("fields",[]):
            color = f.get("color","")
            val_cls = f"val-{color}" if color else ""
            parts.append(f'<div style="margin-bottom:6px"><div style="font-size:10px;color:var(--muted)">{esc(f["label"])}</div><div style="font-size:16px;font-weight:600;font-family:monospace" class="{val_cls}">{esc(f["value"])}</div></div>')
        parts.append('</div>')
    parts.append('</div>')

    return "\n".join(parts)

# ─── Reference generator ───
def gen_reference(data):
    """data = {title, subtitle?, sections: [{title?, items: [{key, value, note?}]}]}
    """
    parts = []
    title = esc(data.get("title","Reference"))
    subtitle = data.get("subtitle","")
    parts.append('<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    for sec in data.get("sections", []):
        parts.append('<div class="card">')
        sec_title = sec.get("title","")
        if sec_title:
            parts.append(f'<div class="section-title">{esc(sec_title)}</div>')
        for item in sec.get("items", []):
            note = item.get("note","")
            note_html = f'<span class="line-note">{esc(note)}</span>' if note else ""
            parts.append(f'<div class="line"><span class="line-label">{esc(item["key"])} {note_html}</span><span class="line-value val-bold">{esc(item["value"])}</span></div>')
        parts.append('</div>')

    return "\n".join(parts)

# ─── Timeline generator ───
def gen_timeline(data):
    """data = {title, subtitle?, events: [{date, title, description?, tag?, tag_color?}]}
    """
    parts = []
    title = esc(data.get("title","Timeline"))
    subtitle = data.get("subtitle","")
    parts.append('<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    parts.append('<div class="card">')
    parts.append('<div class="section-title">Events</div>')
    for ev in data.get("events", []):
        date_str = esc(ev.get("date",""))
        title_str = esc(ev.get("title",""))
        desc = ev.get("description","")
        tag_text = ev.get("tag","")
        tag_color = ev.get("tag_color","blue")

        label = f'<span style="font-weight:500">{title_str}</span>'
        if desc:
            label += f' <span class="line-note">{esc(desc)}</span>'

        value = f'<span class="line-note">{date_str}</span>'
        if tag_text:
            value += tag(tag_text, tag_color)

        parts.append(f'<div class="line"><span class="line-label">{label}</span><span class="line-value">{value}</span></div>')
    parts.append('</div>')

    return "\n".join(parts)

# ─── Checklist generator ───
def gen_checklist(data):
    """data = {title, subtitle?, groups: [{name, items: [{text, done?: bool, note?: string}]}]}
    """
    parts = []
    title = esc(data.get("title","Checklist"))
    subtitle = data.get("subtitle","")
    parts.append('<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    for grp in data.get("groups", []):
        parts.append('<div class="card">')
        grp_name = grp.get("name","")
        if grp_name:
            parts.append(f'<div class="section-title">{esc(grp_name)}</div>')
        for item in grp.get("items", []):
            done = item.get("done", False)
            check = "☑" if done else "☐"
            check_color = "var(--green)" if done else "var(--muted)"
            text_style = "text-decoration:line-through;color:var(--muted)" if done else ""
            note = item.get("note","")
            note_html = f' <span class="line-note">{esc(note)}</span>' if note else ""
            parts.append(f'<div class="line"><span class="line-label" style="{text_style}"><span style="color:{check_color};margin-right:6px">{check}</span>{esc(item["text"])}{note_html}</span></div>')
        parts.append('</div>')

    return "\n".join(parts)

# ─── Dashboard generator ───
def gen_dashboard(data):
    """data = {title, subtitle?, metrics: [{label, value, color?}], notes?: [{title, text}]}
    """
    parts = []
    title = esc(data.get("title","Dashboard"))
    subtitle = data.get("subtitle","")
    parts.append('<div class="card">')
    parts.append(f'<div style="font-size:16px;font-weight:600;margin-bottom:2px">{title}</div>')
    if subtitle:
        parts.append(f'<div style="font-size:12px;color:var(--muted)">{esc(subtitle)}</div>')
    parts.append('</div>')

    metrics = data.get("metrics",[])
    if metrics:
        cols = min(len(metrics), 3)
        parts.append(f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:10px;margin-bottom:10px">')
        for m in metrics:
            color = m.get("color","")
            val_cls = f"val-{color}" if color else ""
            parts.append(f'<div class="card" style="margin-bottom:0;text-align:center;padding:12px 8px">')
            parts.append(f'<div style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:4px">{esc(m["label"])}</div>')
            parts.append(f'<div style="font-size:20px;font-weight:600;font-family:monospace" class="{val_cls}">{esc(m["value"])}</div>')
            parts.append('</div>')
        parts.append('</div>')

    for note in data.get("notes", []):
        parts.append('<div class="card">')
        if note.get("title"):
            parts.append(f'<div class="section-title">{esc(note["title"])}</div>')
        parts.append(f'<div style="font-size:13px;color:var(--fg)">{esc(note["text"])}</div>')
        parts.append('</div>')

    return "\n".join(parts)

# ─── Dispatch ───
GENERATORS = {
    "itinerary": gen_itinerary,
    "report": gen_report,
    "comparison": gen_comparison,
    "reference": gen_reference,
    "timeline": gen_timeline,
    "checklist": gen_checklist,
    "dashboard": gen_dashboard,
}

SCHEMAS = {
    "itinerary": {
        "title": "string",
        "subtitle": "string (optional)",
        "summary": [{"label": "string", "value": "string"}],
        "days": [{"date": "string", "label": "string (optional)",
                  "events": [{"time": "string", "title": "string", "note": "string (optional)", "tag": "string (optional)", "tag_color": "blue|green|red|yellow"}]}]
    },
    "report": {
        "title": "string",
        "subtitle": "string (optional)",
        "sections": [{"title": "string (optional)",
                      "lines": [{"label": "string", "value": "string", "note": "string (optional)", "color": "green|red (optional)"}],
                      "subtotal": {"label": "string", "value": "string"}}]
    },
    "comparison": {
        "title": "string",
        "items": [{"name": "string", "fields": [{"label": "string", "value": "string", "color": "green|red (optional)"}]}]
    },
    "reference": {
        "title": "string",
        "subtitle": "string (optional)",
        "sections": [{"title": "string (optional)", "items": [{"key": "string", "value": "string", "note": "string (optional)"}]}]
    },
    "timeline": {
        "title": "string",
        "subtitle": "string (optional)",
        "events": [{"date": "string", "title": "string", "description": "string (optional)", "tag": "string (optional)", "tag_color": "blue|green|red|yellow"}]
    },
    "checklist": {
        "title": "string",
        "subtitle": "string (optional)",
        "groups": [{"name": "string (optional)", "items": [{"text": "string", "done": "bool (optional)", "note": "string (optional)"}]}]
    },
    "dashboard": {
        "title": "string",
        "subtitle": "string (optional)",
        "metrics": [{"label": "string", "value": "string", "color": "green|red|primary (optional)"}],
        "notes": [{"title": "string (optional)", "text": "string"}]
    },
}

def main():
    p = argparse.ArgumentParser(description="Generate artifact HTML from JSON")
    p.add_argument("--type", "-t", choices=list(GENERATORS.keys()), help="Artifact type")
    p.add_argument("--data", "-d", help="JSON file (default: stdin)")
    p.add_argument("--out", "-o", help="Output HTML file (default: stdout)")
    p.add_argument("--list", "-l", action="store_true", help="Show schemas for all types")
    args = p.parse_args()

    if args.list:
        for name, schema in SCHEMAS.items():
            print(f"\n══ {name} ══")
            print(json.dumps(schema, indent=2))
        return

    if not args.type:
        p.error("--type is required (or use --list)")

    if args.data:
        with open(args.data, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    body = GENERATORS[args.type](data)
    html = HEAD + "\n" + body + "\n" + TAIL

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Written to {args.out}", file=sys.stderr)
    else:
        print(html)

if __name__ == "__main__":
    main()
