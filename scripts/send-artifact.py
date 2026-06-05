#!/usr/bin/env python3
"""Register an artifact and send a web_app button — one command.

Usage:
  # From file (everything auto-detected from env/session context)
  python3 send-artifact.py /tmp/thing.html "Title"

  # Explicit overrides
  python3 send-artifact.py /tmp/thing.html "Title" <host> <chat_id> [thread_id]

Env (read from ~/.hermes/.env):
  TELEGRAM_BOT_TOKEN           — bot token (required)
  HERMES_DASHBOARD_HOST        — public hostname (or pass as CLI arg)
  HERMES_ARTIFACT_CHAT         — default chat_id
  HERMES_ARTIFACT_THREAD       — default thread_id

Session context (set by Hermes gateway via ContextVar bridge):
  HERMES_SESSION_CHAT_ID       — current chat_id (may be stale with concurrent topics)
  HERMES_SESSION_THREAD_ID     — current thread_id (may be stale)

Resolution order for chat_id/thread_id:
  1. CLI argument (highest priority — always use when available)
  2. HERMES_SESSION_* env vars (ContextVar bridge — be aware of staleness)
  3. HERMES_ARTIFACT_* env vars (static fallback)

Exit 0 on success. Prints: OK id=<hex> message_id=<n>
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time


def _load_env() -> None:
    """Load environment from ~/.hermes/.env."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.expanduser("~/.hermes/.env"))
    except ImportError:
        # dotenv not installed — env vars must be set externally
        pass


def _ensure_server(port: int = 9877) -> None:
    """Start artifact-server.py if not already running."""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=2)
        s.close()
        return  # server already up
    except (ConnectionRefusedError, OSError):
        pass

    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_py = os.path.join(script_dir, "artifact-server.py")
    if not os.path.exists(server_py):
        return  # can't start, let register() fail with a clear error

    proc = subprocess.Popen(
        [sys.executable, server_py, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Wait for server to come up (max 5s)
    for _ in range(50):
        time.sleep(0.1)
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1)
            s.close()
            return
        except (ConnectionRefusedError, OSError):
            pass

    # Server failed to start — collect diagnostics
    try:
        _, stderr = proc.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        stderr = b"(server still starting, timed out waiting)"

    if proc.poll() is not None:
        raise RuntimeError(
            f"artifact-server.py exited with code {proc.returncode}. "
            f"stderr: {stderr.decode(errors='replace')[:500]}"
        )


def register(html: str, title: str, port: int = 9877) -> str:
    """Register artifact with the server, return hex ID."""
    import requests

    _ensure_server(port)

    resp = requests.post(
        f"http://localhost:{port}/artifact",
        json={"title": title, "html": html},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


async def _send_button(
    artifact_id: str,
    chat_id: int,
    thread_id: int | None,
    title: str,
    host: str,
) -> int:
    """Send web_app button to Telegram."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env", file=sys.stderr)
        sys.exit(1)

    bot = Bot(token=token)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text=title,
            web_app=WebAppInfo(url=f"https://{host}/artifact/{artifact_id}"),
        )]
    ])

    label = title.replace("Open ", "")
    kwargs: dict[str, object] = {
        "chat_id": chat_id,
        "text": f"{label} \u2014 tap below to open:",
        "reply_markup": kb,
    }
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id

    msg = await bot.send_message(**kwargs)  # type: ignore[arg-type]
    return msg.message_id


def _resolve_env_int(*keys: str) -> int | None:
    """Resolve the first non-empty integer from env vars in priority order."""
    for key in keys:
        raw = os.environ.get(key, "")
        if raw and raw not in ("", "none", "0"):
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def main() -> None:
    _load_env()

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    html_path: str = sys.argv[1]
    title: str = sys.argv[2]

    # Host: CLI arg > env var
    host = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("HERMES_DASHBOARD_HOST", "")
    if not host:
        print("ERROR: host required (pass as arg or set HERMES_DASHBOARD_HOST)", file=sys.stderr)
        sys.exit(1)

    # Chat ID: CLI arg > session env > legacy env
    chat_id = None
    if len(sys.argv) > 4 and sys.argv[4] not in ("", "none"):
        chat_id = int(sys.argv[4])
    if chat_id is None:
        chat_id = _resolve_env_int("HERMES_SESSION_CHAT_ID", "HERMES_ARTIFACT_CHAT")

    # Thread ID: CLI arg > session env > legacy env
    thread_id = None
    if len(sys.argv) > 5 and sys.argv[5] not in ("", "none"):
        thread_id = int(sys.argv[5])
    if thread_id is None:
        thread_id = _resolve_env_int("HERMES_SESSION_THREAD_ID", "HERMES_ARTIFACT_THREAD")

    if chat_id is None:
        print("ERROR: chat_id required (pass as arg or set HERMES_ARTIFACT_CHAT)", file=sys.stderr)
        sys.exit(1)

    # Read HTML
    if html_path == "-":
        html = sys.stdin.read()
    else:
        if not os.path.isfile(html_path):
            print(f"ERROR: file not found: {html_path}", file=sys.stderr)
            sys.exit(1)
        with open(html_path, encoding="utf-8") as f:
            html = f.read()

    # Register
    try:
        artifact_id = register(html, title)
    except Exception as e:
        print(f"ERROR: failed to register artifact: {e}", file=sys.stderr)
        sys.exit(1)

    # Send
    try:
        msg_id = asyncio.run(_send_button(artifact_id, chat_id, thread_id, title, host))
    except Exception as e:
        print(f"ERROR: failed to send message: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK id={artifact_id} message_id={msg_id} chat={chat_id} thread={thread_id or 'none'}")


if __name__ == "__main__":
    main()
