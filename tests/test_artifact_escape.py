"""Tests for the artifact_escape helpers."""

from __future__ import annotations

import artifact_escape as e


class TestEscHtml:
    def test_escapes_all_html_metacharacters(self):
        assert e.esc_html('<a href="x">&\'') == "&lt;a href=&quot;x&quot;&gt;&amp;&#39;"

    def test_plain_text_unchanged(self):
        assert e.esc_html("hello world") == "hello world"

    def test_coerces_non_str(self):
        assert e.esc_html(42) == "42"


class TestJsStr:
    def test_escapes_single_quote(self):
        assert e.js_str("Mom's") == "Mom\\'s"

    def test_escapes_double_quote_and_backslash(self):
        assert e.js_str('a"b\\c') == 'a\\"b\\\\c'

    def test_escapes_newline(self):
        assert e.js_str("a\nb") == "a\\nb"

    def test_neutralizes_script_close(self):
        out = e.js_str("</script>")
        assert "<" not in out
        assert "</script>" not in out
        assert out == "\\x3c/script>"

    def test_escapes_line_separators(self):
        assert e.js_str("a\u2028b\u2029c") == "a\\u2028b\\u2029c"


class TestJsTemplate:
    def test_escapes_backtick_and_interpolation(self):
        assert e.js_template("a`b${c}") == "a\\`b\\${c}"

    def test_escapes_backslash(self):
        assert e.js_template("a\\b") == "a\\\\b"

    def test_neutralizes_script_close(self):
        out = e.js_template("x</script>y")
        assert "<" not in out
        assert "</script>" not in out


class TestJsJson:
    def test_neutralizes_script_close(self):
        out = e.js_json({"k": "</script>"})
        assert "</script>" not in out
        assert "<" not in out
        assert "\\u003c" in out

    def test_escapes_ampersand_and_gt(self):
        out = e.js_json("a&b>c")
        assert "&" not in out
        assert ">" not in out
        assert "\\u0026" in out and "\\u003e" in out

    def test_roundtrips_via_json(self):
        import json

        obj = {"name": "café", "qty": 3, "nested": ["a", "</b>"]}
        # The escapes are valid JSON escapes, so it parses back to the original.
        assert json.loads(e.js_json(obj)) == obj

    def test_preserves_unicode(self):
        assert "长青椒" in e.js_json({"name": "长青椒"})


class TestJsNumber:
    def test_integer(self):
        assert e.js_number(4) == "4"

    def test_float(self):
        assert e.js_number(4.5) == "4.5"

    def test_integral_float_renders_without_decimal(self):
        assert e.js_number(4.0) == "4"

    def test_numeric_string(self):
        assert e.js_number("12") == "12"

    def test_non_numeric_returns_default(self):
        assert e.js_number("4 to 6") == "0"
        assert e.js_number("abc", default="4") == "4"
        assert e.js_number(None) == "0"
