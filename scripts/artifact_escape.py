"""Escaping helpers for safely embedding dynamic data into generated HTML.

The artifact generators inject user-supplied values (titles, items, notes,
CSV/markdown bodies) into HTML and into JavaScript embedded in <script> blocks.
Naive string substitution lets a stray apostrophe break the whole artifact and
lets a literal ``</script>`` close the script element early. These helpers
neutralise both classes of problem while keeping the rendered value intact.
"""

from __future__ import annotations

import json
from typing import Any

# JS line terminators that are illegal (unescaped) inside JS string literals.
_LS = "\u2028"  # LINE SEPARATOR
_PS = "\u2029"  # PARAGRAPH SEPARATOR


def esc_html(value: Any) -> str:
    """Escape for HTML text or double-quoted attribute context."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def js_str(value: Any) -> str:
    """Escape for a single/double-quoted JS string literal inside a <script>.

    Returns the inner content only (no surrounding quotes). ``<`` is emitted as
    ``\\x3c`` so a value like ``</script>`` cannot terminate the script element;
    the escape decodes back to ``<`` at runtime, so displayed text is unchanged.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("<", "\\x3c")
        .replace(_LS, "\\u2028")
        .replace(_PS, "\\u2029")
    )


def js_template(value: Any) -> str:
    """Escape for a backtick template-literal inside a <script> block."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
        .replace("<", "\\x3c")
        .replace(_LS, "\\u2028")
        .replace(_PS, "\\u2029")
    )


def js_json(obj: Any) -> str:
    """``json.dumps`` made safe for embedding in an HTML <script> block.

    Escapes ``<``, ``>``, ``&`` and the JS line terminators so the serialized
    JSON cannot break out of the script element or break a JS string literal.
    """
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(_LS, "\\u2028")
        .replace(_PS, "\\u2029")
    )


def js_number(value: Any, default: str = "0") -> str:
    """Coerce a value to a bare JS numeric literal, or ``default`` if not numeric."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return str(int(num)) if num.is_integer() else str(num)
