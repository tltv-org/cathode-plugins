"""Test HTML template parameter substitution logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

PRESET_DIR = REPO_ROOT / "html-source" / "presets"


class TestTemplateSubstitution:
    """Test the {{KEY}} substitution pattern used by html-source."""

    def test_bumps_has_template_vars(self):
        """bumps.html should have {{KEY}} template variables."""
        content = (PRESET_DIR / "bumps.html").read_text()
        assert "{{DURATION}}" in content
        assert "{{CARDS_JSON}}" in content
        assert "{{GRAIN}}" in content

    def test_weather_has_template_vars(self):
        """weather.html should have {{KEY}} template variables."""
        content = (PRESET_DIR / "weather.html").read_text()
        assert "{{DURATION}}" in content
        assert "{{STYLE}}" in content
        assert "{{WEATHER_DATA}}" in content

    def test_bumps_has_standalone_defaults(self):
        """bumps.html should work standalone (defaults before template block)."""
        content = (PRESET_DIR / "bumps.html").read_text()
        assert "window._cfg" in content, "bumps.html missing standalone defaults"

    def test_weather_has_standalone_defaults(self):
        """weather.html should work standalone (defaults before template block)."""
        content = (PRESET_DIR / "weather.html").read_text()
        assert "window._cfg" in content, "weather.html missing standalone defaults"

    def test_substitution_logic(self):
        """Simulate what html-source does: read HTML, replace {{KEY}} vars."""
        content = (PRESET_DIR / "bumps.html").read_text()

        params = {
            "DURATION": "10",
            "CARDS_JSON": '[{"text":"TEST","duration":5,"position":"center"}]',
            "GRAIN": "true",
            "FADE": "true",
            "FONT_SIZE": "80",
        }

        result = content
        for key, value in params.items():
            result = result.replace("{{" + key + "}}", str(value))

        # All template vars should be resolved
        assert "{{DURATION}}" not in result
        assert "{{CARDS_JSON}}" not in result
        # The substituted values should be present
        assert "10" in result
        assert "TEST" in result

    def test_non_template_presets_have_no_vars(self):
        """Presets that aren't templates shouldn't have unresolved {{}} vars."""
        non_template = [
            "game-of-life",
            "mandelbrot-zoom",
        ]
        for name in non_template:
            content = (PRESET_DIR / f"{name}.html").read_text()
            # These shouldn't have {{KEY}} patterns (quick check)
            import re

            vars_found = re.findall(r"\{\{[A-Z_]+\}\}", content)
            assert not vars_found, (
                f"Non-template preset {name} has template vars: {vars_found}"
            )
