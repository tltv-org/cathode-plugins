"""Validate all source files in the repo parse correctly."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT


def _all_python_files():
    """Collect all .py files in the repo (excluding tests and venv)."""
    return [
        p
        for p in REPO_ROOT.rglob("*.py")
        if ".ruff_cache" not in str(p)
        and "__pycache__" not in str(p)
        and ".venv" not in str(p)
    ]


def _all_json_files():
    return list(REPO_ROOT.rglob("*.json"))


def _all_html_files():
    return list(REPO_ROOT.rglob("*.html"))


class TestPythonSyntax:
    @pytest.mark.parametrize(
        "path",
        _all_python_files(),
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_valid_syntax(self, path):
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {path}: {e}")


class TestJSONValidity:
    @pytest.mark.parametrize(
        "path",
        _all_json_files(),
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_valid_json(self, path):
        content = path.read_text(encoding="utf-8")
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in {path}: {e}")


class TestHTMLFiles:
    @pytest.mark.parametrize(
        "path",
        _all_html_files(),
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_not_empty(self, path):
        content = path.read_text(encoding="utf-8")
        assert len(content) > 50, f"HTML file {path} is suspiciously small"
