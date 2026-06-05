"""Subprocess tests for the CLI scripts (deliver + generators).

These invoke the real scripts the way a user would, validating behaviour the
unit tests can't reach: id-preserving delivery and the generated artifacts'
JavaScript being syntactically valid even with hostile input.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
NODE = shutil.which("node")


def _run(script, args, env_extra=None, stdin=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
        timeout=30,
    )


def _script_blocks(html):
    return re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)


def _assert_valid_js(html):
    blocks = _script_blocks(html)
    assert blocks, "expected at least one <script> block"
    for i, body in enumerate(blocks):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(body)
            tmp = f.name
        try:
            result = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        finally:
            os.unlink(tmp)
        assert result.returncode == 0, f"script block #{i} invalid JS:\n{result.stderr}"


class TestDeliverArtifact:
    def test_preserves_id_no_orphan(self, tmp_path):
        html = tmp_path / "in.html"
        html.write_text("<h1>Delivered</h1>", encoding="utf-8")
        result = _run(
            "deliver-artifact.py",
            ["abc123def456", str(html)],
            env_extra={"HOME": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr

        artifacts = tmp_path / ".hermes" / "artifacts"
        saved = artifacts / "abc123def456.html"
        assert saved.exists()
        assert saved.read_text(encoding="utf-8") == "<h1>Delivered</h1>"

        idx = json.loads((artifacts / "index.json").read_text(encoding="utf-8"))
        assert idx["artifacts"][0]["id"] == "abc123def456"

        # Exactly one html file — no duplicate hash-named orphan.
        assert len(list(artifacts.glob("*.html"))) == 1

    def test_stdin(self, tmp_path):
        result = _run(
            "deliver-artifact.py",
            ["fromstdin01", "-"],
            env_extra={"HOME": str(tmp_path)},
            stdin="<p>piped</p>",
        )
        assert result.returncode == 0, result.stderr
        saved = tmp_path / ".hermes" / "artifacts" / "fromstdin01.html"
        assert saved.read_text(encoding="utf-8") == "<p>piped</p>"

    def test_rejects_non_alnum_id(self, tmp_path):
        html = tmp_path / "in.html"
        html.write_text("<p>x</p>", encoding="utf-8")
        result = _run(
            "deliver-artifact.py",
            ["bad/id", str(html)],
            env_extra={"HOME": str(tmp_path)},
        )
        assert result.returncode == 1
        assert "alphanumeric" in result.stderr

    def test_missing_file(self, tmp_path):
        result = _run(
            "deliver-artifact.py",
            ["okid12345678", str(tmp_path / "nope.html")],
            env_extra={"HOME": str(tmp_path)},
        )
        assert result.returncode == 1
        assert "not found" in result.stderr


class TestGenerateArtifactRendering:
    def test_itinerary_renders_event_title(self, tmp_path):
        # Regression: the event title used to be computed but never rendered.
        data = tmp_path / "it.json"
        data.write_text(
            json.dumps(
                {
                    "title": "Trip",
                    "days": [
                        {"date": "1", "events": [{"time": "9am", "title": "Visit Museum"}]}
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "it.html"
        result = _run(
            "generate-artifact.py",
            ["--type", "itinerary", "--data", str(data), "--out", str(out)],
        )
        assert result.returncode == 0, result.stderr
        html = out.read_text(encoding="utf-8")
        assert "Visit Museum" in html
        assert "9am" in html


@pytest.mark.skipif(NODE is None, reason="node not installed")
class TestGeneratorsProduceValidJs:
    def test_recipe_with_hostile_input(self, tmp_path):
        result = _run(
            "generate-recipe.py",
            [
                "--title", "Mom's </script> Stew",
                "--ingredients", "Beef </script><script>x,500,g",
                "--steps", "Don't burn|Serve",
                "--notes", "Tip's: `code`",
                "--storage-key", "testrecipe",
            ],
        )
        assert result.returncode == 0, result.stderr
        out = Path("/tmp/recipe-testrecipe.html")
        try:
            html = out.read_text(encoding="utf-8")
            _assert_valid_js(html)
            assert len(_script_blocks(html)) == 1  # no breakout into extra blocks
        finally:
            out.unlink(missing_ok=True)

    def test_shopping_with_hostile_input(self, tmp_path):
        data = tmp_path / "items.json"
        data.write_text(
            json.dumps([{"name": "长青椒"}, {"name": "x</script><script>bad"}]),
            encoding="utf-8",
        )
        out = tmp_path / "shop.html"
        result = _run(
            "generate-shopping-list.py",
            ["--title", "Dad's BBQ", "--data", str(data), "--out", str(out)],
        )
        assert result.returncode == 0, result.stderr
        html = out.read_text(encoding="utf-8")
        _assert_valid_js(html)
        assert len(_script_blocks(html)) == 1
        assert "长青椒" in html  # unicode preserved

    def test_csv_with_hostile_input(self, tmp_path):
        csv = tmp_path / "d.csv"
        csv.write_text('Name,Note\n"a</script>b","x`y${z}"\n张三,t\n', encoding="utf-8")
        out = tmp_path / "csv.html"
        result = _run(
            "generate-csv-viewer.py",
            ["--file", str(csv), "--title", "T & <b>", "--out", str(out)],
        )
        assert result.returncode == 0, result.stderr
        html = out.read_text(encoding="utf-8")
        _assert_valid_js(html)
        assert len(_script_blocks(html)) == 1

    def test_markdown_with_hostile_input(self, tmp_path):
        out = tmp_path / "md.html"
        result = _run(
            "generate-markdown-viewer.py",
            ["--md", "# Hi\n`x` </script><script>evil", "--title", "N", "--out", str(out)],
        )
        assert result.returncode == 0, result.stderr
        html = out.read_text(encoding="utf-8")
        _assert_valid_js(html)
        assert len(_script_blocks(html)) == 1

    def test_generate_artifact_report(self, tmp_path):
        data = tmp_path / "r.json"
        data.write_text(
            json.dumps(
                {
                    "title": "R&D <test>",
                    "sections": [
                        {"title": "S", "lines": [{"label": "a<b", "value": "</script>"}]}
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "rep.html"
        result = _run("generate-artifact.py", ["--type", "report", "--data", str(data), "--out", str(out)])
        assert result.returncode == 0, result.stderr
        html = out.read_text(encoding="utf-8")
        _assert_valid_js(html)
        # User data is HTML-escaped, so no raw </script> from the data.
        assert len(_script_blocks(html)) == 1
        assert "&lt;/script&gt;" in html
