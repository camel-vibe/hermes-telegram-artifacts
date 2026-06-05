# hermes-telegram-artifacts

## Architecture
Standalone toolkit for serving interactive HTML artifacts through Telegram bots as Mini Apps.

- `scripts/artifact_server.py` — stdlib threaded HTTP server (port 9877), stores artifacts in `~/.hermes/artifacts/`. `artifact-server.py` is a symlink to it (the documented CLI entry point); the underscore name is the importable module.
- `scripts/artifacts_index.py` — shared, file-locked index operations (register/list/get/delete) with atomic writes and orphan-file cleanup; imported by the server and `deliver-artifact.py`
- `scripts/artifact_escape.py` — HTML/JS escaping helpers shared by the `generate-*` scripts (prevents `</script>` breakout and quote-breakage)
- `scripts/send-artifact.py` — one-shot: register HTML + send web_app button via Bot API
- `scripts/deliver-artifact.py` — save HTML under a given id + register it (no API call)
- `scripts/register-artifact.py` — register via HTTP (no Telegram send)
- `scripts/generate-artifact.py` — generate HTML from structured JSON (itinerary, report, comparison, etc.); plus `generate-{csv-viewer,markdown-viewer,recipe,shopping-list}.py`
- `templates/` — HTML templates with `{{PLACEHOLDER}}` tokens
- `references/` — design system, Mini App API, delivery patterns

## Key Commands
- Start server: `python3 scripts/artifact-server.py [--port 9877]`
- Send artifact: `python3 scripts/send-artifact.py /tmp/thing.html "Title" <host> [chat_id] [thread_id]`
- Register artifact: `python3 scripts/register-artifact.py file.html "Title"`

## Code Standards
- Python 3.10+
- artifact-server.py is stdlib only
- send-artifact.py requires python-telegram-bot, python-dotenv, requests
- Use type hints where possible
- Keep HTML under 100KB
- Use event delegation for JS, no inline onclick
- Env var resolution order: CLI arg > HERMES_SESSION_* (ContextVar bridge) > HERMES_ARTIFACT_* (static)
