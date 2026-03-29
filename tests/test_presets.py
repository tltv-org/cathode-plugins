"""Test that all preset files exist, parse correctly, and are well-formed."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

# ── Expected presets per plugin ──────────────────────────────────────────

HTML_PRESETS = [
    "bumps",
    "seance",
    "weather",
    "channel_zero",
    "channel-one-intro",
    "game-of-life",
    "mandelbrot-zoom",
]

SCRIPT_PRESETS = [
    "geometric_shapes",
    "color_bars_glitch",
    "ascii_text_wave",
    "emergency_broadcast",
    "pixel_sort_corruption",
    "retro_computer_boot",
    "scan_line_tv_static",
    "youtube_poop_chaos",
]

GSTREAMER_PRESETS = [
    "smpte-with-tone",
    "bars-silent",
    "snow",
]


# ── HTML presets ─────────────────────────────────────────────────────────


class TestHTMLPresets:
    PRESET_DIR = REPO_ROOT / "html-source" / "presets"

    @pytest.mark.parametrize("name", HTML_PRESETS)
    def test_preset_exists(self, name):
        path = self.PRESET_DIR / f"{name}.html"
        assert path.exists(), f"Missing HTML preset: {name}.html"

    @pytest.mark.parametrize("name", HTML_PRESETS)
    def test_preset_not_empty(self, name):
        path = self.PRESET_DIR / f"{name}.html"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100, (
            f"HTML preset {name} seems too small ({len(content)} bytes)"
        )

    @pytest.mark.parametrize("name", HTML_PRESETS)
    def test_preset_has_html_structure(self, name):
        path = self.PRESET_DIR / f"{name}.html"
        content = path.read_text(encoding="utf-8").lower()
        assert "<html" in content or "<!doctype" in content or "<canvas" in content, (
            f"HTML preset {name} doesn't look like valid HTML"
        )

    def test_no_unexpected_presets(self):
        """Catch presets that exist on disk but aren't in the expected list."""
        actual = {p.stem for p in self.PRESET_DIR.glob("*.html")}
        expected = set(HTML_PRESETS)
        extra = actual - expected
        assert not extra, f"Unexpected HTML presets on disk: {extra}"


# ── Script presets ───────────────────────────────────────────────────────


class TestScriptPresets:
    PRESET_DIR = REPO_ROOT / "script-source" / "presets"

    @pytest.mark.parametrize("name", SCRIPT_PRESETS)
    def test_preset_exists(self, name):
        path = self.PRESET_DIR / f"{name}.py"
        assert path.exists(), f"Missing script preset: {name}.py"

    @pytest.mark.parametrize("name", SCRIPT_PRESETS)
    def test_preset_valid_python(self, name):
        """Every script preset must be valid Python syntax."""
        path = self.PRESET_DIR / f"{name}.py"
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Script preset {name} has syntax error: {e}")

    @pytest.mark.parametrize("name", SCRIPT_PRESETS)
    def test_preset_imports_pillow(self, name):
        """Script presets should use Pillow for frame generation."""
        path = self.PRESET_DIR / f"{name}.py"
        source = path.read_text(encoding="utf-8")
        assert "from PIL" in source or "import PIL" in source, (
            f"Script preset {name} doesn't import Pillow"
        )

    @pytest.mark.parametrize("name", SCRIPT_PRESETS)
    def test_preset_writes_stdout(self, name):
        """Script presets must write raw frames to stdout."""
        path = self.PRESET_DIR / f"{name}.py"
        source = path.read_text(encoding="utf-8")
        assert "sys.stdout" in source, f"Script preset {name} doesn't write to stdout"

    @pytest.mark.parametrize("name", SCRIPT_PRESETS)
    def test_preset_reads_env_vars(self, name):
        """Script presets should read WIDTH/HEIGHT/FPS from environment."""
        path = self.PRESET_DIR / f"{name}.py"
        source = path.read_text(encoding="utf-8")
        for var in ("WIDTH", "HEIGHT", "FPS"):
            assert var in source, f"Script preset {name} doesn't read {var} from env"

    def test_no_unexpected_presets(self):
        actual = {p.stem for p in self.PRESET_DIR.glob("*.py") if p.stem != "__init__"}
        expected = set(SCRIPT_PRESETS)
        extra = actual - expected
        assert not extra, f"Unexpected script presets on disk: {extra}"


# ── GStreamer presets ────────────────────────────────────────────────────


class TestGStreamerPresets:
    PRESET_DIR = REPO_ROOT / "gstreamer-source" / "presets"

    @pytest.mark.parametrize("name", GSTREAMER_PRESETS)
    def test_preset_exists(self, name):
        path = self.PRESET_DIR / f"{name}.json"
        assert path.exists(), f"Missing GStreamer preset: {name}.json"

    @pytest.mark.parametrize("name", GSTREAMER_PRESETS)
    def test_preset_valid_json(self, name):
        path = self.PRESET_DIR / f"{name}.json"
        content = path.read_text(encoding="utf-8")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            pytest.fail(f"GStreamer preset {name} is invalid JSON: {e}")
        assert isinstance(data, dict), f"GStreamer preset {name} root must be an object"

    @pytest.mark.parametrize("name", GSTREAMER_PRESETS)
    def test_preset_has_required_fields(self, name):
        path = self.PRESET_DIR / f"{name}.json"
        data = json.loads(path.read_text())
        assert "name" in data, f"GStreamer preset {name} missing 'name'"
        assert "description" in data, f"GStreamer preset {name} missing 'description'"

    def test_no_unexpected_presets(self):
        actual = {p.stem for p in self.PRESET_DIR.glob("*.json")}
        expected = set(GSTREAMER_PRESETS)
        extra = actual - expected
        assert not extra, f"Unexpected GStreamer presets on disk: {extra}"


# ── Overlay presets ──────────────────────────────────────────────────────


class TestOverlayPresets:
    PRESET_DIR = REPO_ROOT / "overlay" / "presets"

    def test_bug_preset_exists(self):
        path = self.PRESET_DIR / "bugs" / "channel-id.json"
        assert path.exists(), "Missing overlay preset: bugs/channel-id.json"

    def test_ticker_preset_exists(self):
        path = self.PRESET_DIR / "tickers" / "default.json"
        assert path.exists(), "Missing overlay preset: tickers/default.json"

    def test_bug_preset_valid_json(self):
        path = self.PRESET_DIR / "bugs" / "channel-id.json"
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_ticker_preset_valid_json(self):
        path = self.PRESET_DIR / "tickers" / "default.json"
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
