"""Shared test fixtures — mock cathode imports so plugins can be loaded standalone."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Root dirs ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIRS = {
    "html-source": REPO_ROOT / "html-source",
    "script-source": REPO_ROOT / "script-source",
    "gstreamer-source": REPO_ROOT / "gstreamer-source",
    "overlay": REPO_ROOT / "overlay",
}


# ── Mock FilePresetStore ─────────────────────────────────────────────────


class FakePresetStore:
    """Minimal FilePresetStore replacement for testing."""

    def __init__(self, directory="", extension="", category=None):
        self.directory = directory
        self.extension = extension
        self.category = category
        self._dir = Path(directory)

    def list(self):
        if not self._dir.exists():
            return []
        return [
            {"name": p.stem, "filename": p.name}
            for p in sorted(self._dir.glob(f"*{self.extension}"))
            if p.is_file()
        ]

    def get(self, name):
        # Try with and without extension
        path = self._dir / f"{name}{self.extension}"
        if not path.exists():
            path = self._dir / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Non-JSON presets (HTML, Python) — return metadata
            return {"name": name, "path": str(path)}

    def save(self, name, data):
        return True

    def delete(self, name):
        return True


# ── Mock 'plugins' module ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_plugins_module():
    """Inject a fake 'plugins' module so `from plugins import FilePresetStore` works."""
    mod = types.ModuleType("plugins")
    mod.FilePresetStore = FakePresetStore
    sys.modules["plugins"] = mod
    yield mod
    sys.modules.pop("plugins", None)


# ── Mock 'main' module ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_main_module():
    """Inject a fake 'main' module so overlay's _get_engine() doesn't crash."""
    mod = types.ModuleType("main")
    engine = MagicMock()
    engine.is_running = False
    engine.get_overlay_element = MagicMock(return_value=None)
    mod.playout = engine
    sys.modules["main"] = mod
    yield mod
    sys.modules.pop("main", None)


# ── Mock routes.playout ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_routes_playout():
    """Mock routes.playout._parse_text_color used by overlay."""
    routes = types.ModuleType("routes")
    playout = types.ModuleType("routes.playout")

    def _parse_text_color(color_str):
        # Return a dummy ARGB uint
        return 0xFFFFFFFF

    playout._parse_text_color = _parse_text_color
    routes.playout = playout
    sys.modules["routes"] = routes
    sys.modules["routes.playout"] = playout
    yield
    sys.modules.pop("routes.playout", None)
    sys.modules.pop("routes", None)


# ── Plugin loader helpers ────────────────────────────────────────────────


def _load_plugin(name):
    """Import a plugin's __init__.py and return the module.

    Re-imports fresh each time to avoid stale state.
    """
    plugin_dir = PLUGIN_DIRS[name]
    module_name = f"_plugin_{name.replace('-', '_')}"

    # Remove cached version
    sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(
        module_name, plugin_dir / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def html_source_module():
    return _load_plugin("html-source")


@pytest.fixture()
def script_source_module():
    return _load_plugin("script-source")


@pytest.fixture()
def gstreamer_source_module():
    return _load_plugin("gstreamer-source")


@pytest.fixture()
def overlay_module():
    return _load_plugin("overlay")


# ── Mock FastAPI app ─────────────────────────────────────────────────────


class FakeApp:
    """Minimal stand-in for cathode's PluginApp wrapper."""

    def __init__(self):
        self.routers = []

    def include_router(self, router):
        self.routers.append(router)


@pytest.fixture()
def fake_app():
    return FakeApp()
