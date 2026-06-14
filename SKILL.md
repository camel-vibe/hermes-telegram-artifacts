---
name: "artifact-builder"
description: "Use when build interactive HTML artifacts for the Telegram Mini App. Use for ANYTHING that benefits from being visual/interactive: recipes (with portion calculators), shopping lists (with localStorage), calculators, charts, diagrams, reference sheets, reports, and tools. When a user asks for food, recipes, meal planning, shopping, groceries, or anything that could be an interactive widget \u2014 build an artifact."
version: "2.7.0"
author: "hermes"
platforms: ["linux"]
metadata:
  hermes:
    tags: ["artifacts", "visualization", "mini-app", "dashboard", "charts", "interactive", "diagrams", "recipes", "cooking", "food", "shopping-lists", "personal-tools", "calculators"]
    category: "creative"
----

# Artifact Builder

Generate interactive HTML artifacts that render in the Telegram Mini App.

## TL;DR — 2 Steps

```bash
# 1. Write HTML to /tmp/thing.html (use template below)
# 2. Send it:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/send-artifact.py \
  /tmp/thing.html "Title" <host> [chat_id] [thread_id]
```

**Host is required** (or set `HERMES_DASHBOARD_HOST` in `~/.hermes/.env`). Chat_id and thread_id can come from env vars — pass explicitly for reliability.

### Env vars in `~/.hermes/.env`

```bash
TELEGRAM_BOT_TOKEN=***             # auto-loaded (already there if Hermes is configured)
HERMES_DASHBOARD_HOST=your-host.com  # Tailscale Funnel / nginx host
HERMES_ARTIFACT_CHAT=123456789     # default chat_id (optional)
HERMES_ARTIFACT_THREAD=999         # default thread_id (optional)
```

### Resolving chat_id and thread_id

Each conversation is a topic inside one DM chat. The session context shows `thread: <N>` which is the **thread_id** (topic number), NOT the chat_id.

**Resolution order for send-artifact.py:**
1. CLI args (highest priority)
2. `HERMES_SESSION_THREAD_ID` / `HERMES_SESSION_CHAT_ID` from env (ContextVar bridge — can be stale!)
3. `HERMES_ARTIFACT_THREAD` / `HERMES_ARTIFACT_CHAT` env vars (reliable fallback)

**The thread_id from the ContextVar bridge may be wrong** when multiple DM topics are active concurrently. If the artifact lands in the wrong topic, pass thread_id explicitly from the session context header (`thread: <N>`).

**Never use the thread_id number as the chat_id.** They are different values.

## When to Use

**Use proactively.** Don't wait for the user to ask for a visualization. If a response contains 3+ numeric data points, a chart is better than prose. If explaining something interactive helps, build it.

**Always build artifacts for:**
- Any recipe → artifact with portion calculator
- Shopping lists, groceries → persistent checklist with localStorage
- Charts, data visualization → inline SVG or Chart.js
- Calculators, converters, reference tools
- Reports, comparisons, timelines, itineraries
- Architecture diagrams, flowcharts (SVG/Canvas)
- Anything where interaction > reading

**Don't build for:** Simple answers (1-2 numbers), text-only responses, quick lookups.

## Architecture

```
Agent writes HTML → artifact-server.py (port 9877) → stored on disk
                                            ↓
send-artifact.py → Bot API web_app button → https://your-host/artifact/<id>
                                            ↓
                                User taps → Mini App panel slides up
```

**Prerequisites:**
1. `HERMES_DASHBOARD_HOST` and `HERMES_ARTIFACT_CHAT` set in `~/.hermes/.env`
2. `TELEGRAM_BOT_TOKEN` auto-loaded from `~/.hermes/.env` (already there if Hermes is configured)
3. HTTPS endpoint (Tailscale Funnel, nginx, caddy, etc.)

**The agent must assume the artifact server is running.** `send-artifact.py` auto-starts it if needed — never waste a turn checking `curl localhost:9877` or `pgrep artifact-server`. Just build the HTML and send it.

**Standalone (no Hermes):** https://github.com/camel-vibe/hermes-telegram-artifacts

## How to Deliver an Artifact

### Method 1: send-artifact.py (standalone, proven)

```bash
# Pass host explicitly, or rely on HERMES_DASHBOARD_HOST env var:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/send-artifact.py \
  /tmp/thing.html "Title" <host> [chat_id] [thread_id]
```

- Registers the artifact with the artifact server (port 9877)
- Sends a `web_app` button via Bot API to the target chat/thread
- **Do NOT rely on env var defaults for thread_id** — extract from session context header

### Method 2: send_message with ARTIFACT: prefix (gateway-integrated)

```python
send_message(message="Here's the report:\n\nARTIFACT:<id> Report Title", target="telegram:<chat_id>:<thread_id>")
```

- The gateway adapter strips the `ARTIFACT:<id>` tag and sends a `web_app` button on the first chunk
- Requires the gateway to be running (picks up the button on next restart)
- **The tag must NOT be the only content** — if stripped text is empty, send_message rejects it
- Less reliable than `send-artifact.py` during Tailscale Funnel flapping (gateway adds latency)

### API Endpoints

- `POST /artifact` — register: `{"title": "...", "html": "..."}` → `{"id": "...", ...}`
- `GET /artifact/<id>` — serve HTML (with TG lifecycle injections)
- `GET /artifact/latest` — serve the most recent artifact
- `GET /artifacts` — JSON list: `{"artifacts": [{id, title, type, timestamp, age}, ...]}`
- `GET /artifacts/all` — **gallery page** (HTML): latest expanded with iframe, rest collapsed, Open/Delete buttons
- `GET /artifacts/latest-age` — age in seconds of latest artifact
- `DELETE /artifact/<id>` — remove

**Note:** All endpoints are served by the standalone `artifact-server.py` (bundled with this skill). No webui patches needed.

## Starter Template

```html
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {
  --bg: var(--tg-theme-bg-color, #f5f5f5);
  --card: var(--tg-theme-section-bg-color, #ffffff);
  --fg: var(--tg-theme-text-color, #1a1a1a);
  --muted: var(--tg-theme-hint-color, #666);
  --accent: var(--tg-theme-accent-text-color, #0ea5e9);
  --border: var(--tg-theme-section-separator-color, #e0e0e0);
  --green: #16a34a; --red: #dc2626; --yellow: #d97706;
}
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--fg); padding: 16px }
.card { background: var(--card); border: 0.5px solid var(--border); border-radius: 12px; padding: 14px; margin-bottom: 10px }
.label { font-size: 12px; color: var(--muted); margin-bottom: 6px }
.value { font-size: 24px; font-weight: 600 }
</style>
</head>
<body>

<div class="card">
  <div class="label">Your metric</div>
  <div class="value">42</div>
</div>

<script>
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
if (tg) {
  try {
    tg.ready();
    tg.setHeaderColor(tg.themeParams?.bg_color || '#f5f5f5');
    tg.setBackgroundColor(tg.themeParams?.bg_color || '#f5f5f5');
    tg.onEvent('themeChanged', function() {
      var p = tg.themeParams;
      if (p) { tg.setHeaderColor(p.bg_color); tg.setBackgroundColor(p.bg_color); }
    });
  } catch(e) { console.error('[TG]', e); }
}
</script>
</body>
</html>
```

**Key:** Use `--tg-theme-*` CSS variables directly. They auto-adapt to ALL Telegram themes. No JS theme override needed — the CSS vars handle it. Only call `setHeaderColor`/`setBackgroundColor` to sync the chrome.

Full template: `references/template.html`

## Theme System

Telegram's WebView injects CSS custom properties automatically:

```css
--tg-theme-bg-color          /* page background */
--tg-theme-text-color        /* main text */
--tg-theme-hint-color        /* secondary/muted text */
--tg-theme-accent-text-color /* links, accent */
--tg-theme-section-bg-color  /* card/section background */
--tg-theme-section-separator-color /* borders */
```

Use them as fallback values in `:root` — works in browser preview AND Telegram.

In JS, only sync the header/background bar colors (CSS vars don't reach the Telegram chrome):
```js
tg.setHeaderColor(tg.themeParams?.bg_color || '#f5f5f5');
tg.setBackgroundColor(tg.themeParams?.bg_color || '#f5f5f5');
```

## Mini App Behavior

- **Compact mode:** The artifact server injects `tg.exitFullscreen()` so artifacts open at half-screen. If you need full-screen, call `tg.requestFullscreen()` in your artifact's JS.
- **BackButton:** Auto-registers when modal is open, pops modal on press.
- **Lifecycle:** `tg.onEvent('activated')` / `tg.onEvent('deactivated')` for pause/resume.

## Storage Options

- **localStorage** — works in Mini App iframe, persists across sessions. iOS may expire after ~7 days of disuse.
- **tg.CloudStorage** — cross-device synced, 1024 items. Best for user preferences.
- **tg.DeviceStorage** — 5MB local (Bot API 9.0+).
- **tg.SecureStorage** — 10 items in OS keychain (Bot API 9.0+).

## Available CDN Libraries

- **Chart.js 4.4.1**: `cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js`
- **D3 7.8.5**: `cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js`
- **Mermaid 11**: `esm.sh/mermaid@11/dist/mermaid.esm.min.mjs`

## Component Patterns

### Metric Grid
```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px">
  <div class="card">
    <div class="label">Label</div>
    <div class="value">42</div>
  </div>
</div>
```

### Progress Bar
```html
<div class="progress">
  <div class="progress-fill" style="width:65%;background:var(--green)"></div>
</div>
```

### Line Items
```html
<div class="card">
  <div class="line"><span class="line-label">Item</span><span class="line-value">$12.00</span></div>
  <div class="line"><span class="line-label">Total</span><span class="line-value" style="font-weight:600">$12.00</span></div>
</div>
```

### SVG Line Chart (no library needed)
```js
function drawChart(points, el) {
  let W = el.clientWidth || 300, H = 160;
  let maxVal = Math.max(...points.map(p => p.value), 1);
  let n = points.length;
  let x = i => (i/(n-1)) * W;
  let y = v => H - (v/maxVal) * H;
  let line = 'M' + points.map((p,i) => x(i)+','+y(p.value)).join(' L');
  let area = line + ' L'+x(n-1)+','+y(0)+' L'+x(0)+','+y(0)+' Z';
  el.innerHTML = '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'
    + '<path d="'+area+'" fill="rgba(14,165,233,0.1)"/>'
    + '<path d="'+line+'" fill="none" stroke="var(--accent)" stroke-width="2"/>'
    + '</svg>';
}
```

## Structured Path (generate-artifact.py)

For data-driven artifacts, write JSON and generate:

```bash
python3 ~/.hermes/skills/creative/artifact-builder/scripts/generate-artifact.py --list  # see types
python3 generate-artifact.py --type itinerary --data trip.json --out trip.html
python3 register-artifact.py trip.html "Trip Itinerary"
```

**Types:** itinerary, report, comparison, reference, timeline, checklist, dashboard

### CSV viewer (dedicated template)

```bash
# From a CSV file:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/generate-csv-viewer.py \
  --file data.csv --title "Employee data"

# Inline CSV string:
python3 generate-csv-viewer.py --csv "Name,Score\nAlice,95\nBob,87"

# Pipe:
cat data.csv | python3 generate-csv-viewer.py --stdin --title "Scores"

# Then send:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/send-artifact.py \
  /tmp/csv-viewer-employee-data.html "Employee data" <host> <chat_id> <thread_id>
```

**Features:** auto-detects numeric columns (right-aligned, comma-formatted), real-time search with highlight, click-to-sort columns, row/column stats bar. Works with any CSV — just pipe data in.

**Template:** `templates/csv-viewer.html`. **Script:** `scripts/generate-csv-viewer.py`. Placeholders: `{{TITLE}}`, `{{CSV_DATA}}`.

### Markdown viewer (dedicated template)

```bash
# From a markdown file:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/generate-markdown-viewer.py \
  --file notes.md --title "Meeting notes"

# Inline:
python3 generate-markdown-viewer.py --md "# Title\nSome **bold** text" --title "Quick note"

# Pipe:
cat doc.md | python3 generate-markdown-viewer.py --stdin --title "Docs"

# Then send:
python3 ~/.hermes/skills/creative/artifact-builder/scripts/send-artifact.py \
  /tmp/markdown-viewer-meeting-notes.html "Meeting notes" <host> <chat_id> <thread_id>
```

**Features:** renders headings, bold, italic, strikethrough, inline code, fenced code blocks, blockquotes, ordered/unordered lists, tables, links, horizontal rules. No external deps — pure JS parser. Word/line count in meta bar.

**Template:** `templates/markdown-viewer.html`. **Script:** `scripts/generate-markdown-viewer.py`. Placeholders: `{{TITLE}}`, `{{MARKDOWN_DATA}}`.

## Design Guidelines

- **Flat** — no gradients, drop shadows, blur
- **Compact** — essential info, not paragraphs
- **Two font weights:** 400 and 500 (600 for values)
- **Rounded corners:** 12px cards, 8px inner
- **Border:** 0.5px always
- **No emoji** — use text or icons
- **Sentence case** — never Title Case

## Mobile-First (360–400px width)

- Single column layout
- Large touch targets (44px+)
- No hover-only interactions
- No horizontal scroll
- No `position: fixed` — use flexbox/grid
- Font sizes 12–15px

## If Artifacts Don't Work (Read This First)

Before exploring alternatives or questioning the approach, check these in order:

1. **Artifact server running?** `curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:9877/artifact/<id>"` — should return 200. If not, start it: `python3 ~/.hermes/skills/creative/artifact-builder/scripts/artifact-server.py`
2. **Public URL works?** `curl -s -o /dev/null -w "%{http_code}" "https://<your-host>/artifact/<id>"` — should return 200. If local works but public doesn't, check your reverse proxy / Tailscale Funnel config.
3. **Adapter configured?** The adapter reads the host from its config. If the URL in the `web_app` button points to `localhost` instead of your public host, check the adapter's artifact delivery code.
4. **Gateway running?** `pgrep -f "gateway run"` — if dead, restart with `hermes gateway restart`.
5. **Still stuck?** Read the Pitfalls section below. Do NOT explore deep links, compact mode, inline queries, or other alternatives — the `web_app` button is the proven approach.

## Pitfalls

- **ARTIFACT: prefix needs visible text.** When using `send_message` with `ARTIFACT:<id> [title]`, the tag is stripped from the content before sending. If the tag is the ONLY content, send_message rejects it ("No deliverable text or media remained after processing MEDIA tags"). Always include at least one line of visible text alongside the tag. Example: `"Here's the report:\n\nARTIFACT:abc123 Report"`.
- **`#grid` innerHTML wipe:** The dashboard's `render()` calls `E.grid.innerHTML = cards` every 30s. `#modal-overlay`, `#error`, `#pull-ind` MUST be siblings of `#grid`, not children.
- **WebView caching:** After editing dashboard HTML, add `<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">`. On Android, Force Stop Telegram (not just clear cache).
- **TG init try/catch:** Wrap the entire `if(tg){...}` block. If ANY call throws (e.g. `setParams` with unsupported field), everything after it dies — cards stop opening, UI freezes.
- **SecondaryButton transparent bg:** Invisible on all themes. Use `rgba(14,165,233,0.12)` instead.
- **Native popups:** Replace `confirm()` with `tg.showConfirm()` and `alert()` with `tg.showAlert()`. Fall back to browser versions when `tg` isn't available.
- **Don't include `<h2>` title** in artifact HTML — the dashboard hero header already shows it.
- **localStorage on iOS:** May expire after ~7 days of disuse. Use `tg.CloudStorage` for critical prefs.
- **E object init order:** `E.ts`, `E.dot` etc. are only valid after `render()` inserts nav HTML. Don't reference before first `render()` call.
- **DOM creation order:** `#artifacts-view` created first, then `.top-nav` and `.tabs` by `render()`. Don't change insertion order without checking.
- **Gateway restart:** Changes to `gateway/platforms/telegram.py` need a restart before taking effect. A `send_message` in the same turn uses the OLD code.
- **Always pass `chat_id` and `thread_id` explicitly to `send-artifact.py`.** The env var bridge (`HERMES_SESSION_THREAD_ID`) is unreliable due to concurrent session clobbering — `set_current_session_id()` writes to process-global `os.environ`, and when two DM topics are active, the later one overwrites the earlier's value. Extract `thread_id` from your session context header (`thread: XXXX`) and pass it as the last CLI argument.
- **Don't overcomplicate delivery.** The `web_app` button works. If the user says "it was working before, just do that" — revert to the working approach and stop exploring alternatives mid-conversation. Novel approaches (deep links, compact mode, inline queries) should be tested in isolation, not mixed into the delivery path that's already working.
- **Button type must be `web_app`, not `url`.** A URL button pointing to `t.me/bot?startapp=artifact:<id>&mode=compact` does NOT work — it opens Telegram's deep link handler, not a WebView. The button MUST use `web_app=WebAppInfo(url="https://host/artifact/<id>")` to open the artifact as a Mini App. The gateway adapter and send_message_tool both handle this correctly, but if you're writing custom delivery code, use `web_app`, not `url`.
- **Artifact server must be running and publicly accessible.** The adapter sends `web_app` buttons pointing to `https://<host>/artifact/<id>`. If that URL returns 404 or 502, check the artifact server (`artifact-server.py`) is running and your reverse proxy routes to it.
- **Building HTML pages in Python: use event delegation, not inline onclick.** When generating HTML with embedded JS in a Python string, nested quote escaping becomes a nightmare (`\\\\'` vs `\\'` vs `'`). Instead of `onclick="del('${id}')"`, build DOM elements with `document.createElement()` and attach a single event listener on a parent container that reads `data-id` attributes. See `_gallery_html()` in `artifact-server.py` for the pattern.
- **Tailscale Funnel 502 after service restart is transient.** The Funnel proxy returns 502 while the backend (pi-sidecar, artifact-server) is warming up caches or initializing. Wait 2-3 seconds and retry — it's not a real failure.


## References

- `references/telegram-miniapp-delivery.md` — delivery patterns, BotFather setup, env var decisions
- `references/claude-design-system.md` — design tokens and patterns
- `references/telegram-miniapp-api.md` — Mini App API reference
- `references/telegram-inline-capabilities.md` — inline query capabilities
- `references/webui-artifact-route.md` — WebUI artifact routing
- `references/pi-sidecar-artifact-infra.md` — Pi sidecar infrastructure

## What Doesn't Work (Don't Try)

- **`answerWebAppQuery`** — deliberately excluded. Requires `query_id` from `tg.initDataUnsafe.query_id`, which is only available when the Mini App was opened via a `web_app` button. Even then, the resulting inline result card is a weak preview (title + description). The `web_app` button IS the UX — no need for a secondary card.
- **`mode=compact` via `web_app` buttons** — only works with Main Mini App deep links (`t.me/bot?startapp=...&mode=compact`), NOT `web_app` buttons. To get half-screen delivery, use a URL button with the deep link instead. The dashboard must consume `tg.startParam` to navigate to the artifact. See `references/telegram-miniapp-delivery.md` for the pattern. Works but adds complexity — use `web_app` buttons unless half-screen is specifically needed.
- **`InlineQueryResultWebApp`** — not in python-telegram-bot 22.x. Would require raw Bot API calls and user typing `@botname` first.
- **Rendering HTML inline in chat** — Telegram doesn't support this. The `web_app` button IS the right UX.
- **Packaging as a Hermes plugin** — The plugin system supports hooks, tools, providers, and platform adapters, but has no mechanism to add HTTP routes or start background servers. Artifact serving requires a standalone server (`artifact-server.py`) or a reverse proxy route. The server is bundled with the skill — just run it.
- **Don't bundle environment-specific code with the portable skill.** Keep the standalone `artifact-server.py` free of homelab-specific infrastructure (custom sidecars, hostnames, etc.). Anyone should be able to run it without your specific setup. The portable version lives at https://github.com/camel-vibe/hermes-telegram-artifacts

## Full Example

```html
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:var(--tg-theme-bg-color,#f5f5f5);--card:var(--tg-theme-section-bg-color,#fff);--fg:var(--tg-theme-text-color,#1a1a1a);--muted:var(--tg-theme-hint-color,#666);--accent:var(--tg-theme-accent-text-color,#0ea5e9);--border:var(--tg-theme-section-separator-color,#e0e0e0);--green:#16a34a;--red:#dc2626}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:16px}
.card{background:var(--card);border:0.5px solid var(--border);border-radius:12px;padding:14px;margin-bottom:10px}
.label{font-size:12px;color:var(--muted);margin-bottom:6px}
.value{font-size:24px;font-weight:600}
.progress{height:4px;background:var(--border);border-radius:2px;overflow:hidden;margin:4px 0}
.progress-fill{height:100%;border-radius:2px}
</style>
</head>
<body>
<div class="card">
  <div class="label">Root partition</div>
  <div class="value">30.2 / 136.5 GiB</div>
  <div class="progress"><div class="progress-fill" style="width:22%;background:var(--green)"></div></div>
</div>
<script>
const tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;
if(tg){try{tg.ready();tg.setHeaderColor(tg.themeParams?.bg_color||'#f5f5f5');tg.setBackgroundColor(tg.themeParams?.bg_color||'#f5f5f5');tg.onEvent('themeChanged',function(){var p=tg.themeParams;if(p){tg.setHeaderColor(p.bg_color);tg.setBackgroundColor(p.bg_color);}});}catch(e){console.error('[TG]',e);}}
</script>
</body>
</html>
```
