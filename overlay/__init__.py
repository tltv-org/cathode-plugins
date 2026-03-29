"""overlay — Post-mix graphics overlay plugin.

Registers overlay elements that are inserted into the mixer pipeline
between the compositor output and the output inter sinks.  When this
plugin is loaded, the mixer pipeline becomes:

    compositor → comp_caps → textoverlay → gdkpixbufoverlay → rsvgoverlay → mix_vsink

When NOT loaded, the mixer is pure:

    compositor → comp_caps → mix_vsink

Category: graphics
System deps: none (textoverlay, gdkpixbufoverlay, rsvgoverlay are in
gst-plugins-base/good, already installed in all image variants)
Image: works on both cathode:slim and cathode:latest

Overlay types:
- text-overlay: GStreamer textoverlay (text, tickers, "coming up next")
- bug-overlay: gdkpixbufoverlay (channel logo PNG/JPEG in corner)
- svg-overlay: rsvgoverlay (scalable vector graphics)

All overlays start hidden (alpha=0 or silent=True).  Plugin routes
control them at runtime by setting GObject properties.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/overlay", tags=["plugins"])


# ── Overlay element access (set during register, used by routes) ──

_engine_ref = None


def _get_engine():
    """Get the playout engine."""
    global _engine_ref
    if _engine_ref is not None:
        return _engine_ref
    try:
        import main

        return main.playout
    except (ImportError, AttributeError):
        return None


def _get_overlay(name: str):
    """Get a named overlay element from the engine's mixer."""
    engine = _get_engine()
    if engine:
        return engine.get_overlay_element(name)
    return None


# ══════════════════════════════════════════════════════════════════
# Routes — /api/overlay/*
# ══════════════════════════════════════════════════════════════════


@router.get("/status")
async def overlay_status():
    """Current state of all overlay elements."""
    engine = _get_engine()
    if not engine or not engine.is_running:
        return {"active": False, "overlays": {}}

    result = {}

    # Text overlay
    text_elem = _get_overlay("text-overlay")
    if text_elem:
        result["text"] = {
            "active": not text_elem.get_property("silent"),
            "text": text_elem.get_property("text"),
        }

    # Bug overlay
    bug_elem = _get_overlay("bug-overlay")
    if bug_elem:
        result["bug"] = {
            "active": bug_elem.get_property("alpha") > 0,
            "location": bug_elem.get_property("location") or None,
            "alpha": bug_elem.get_property("alpha"),
        }

    # SVG overlay
    svg_elem = _get_overlay("svg-overlay")
    if svg_elem:
        result["svg"] = {
            "active": getattr(svg_elem.props, "width_relative", 0) > 0,
        }

    return {"active": True, "overlays": result}


@router.post("/text")
async def set_text(
    text: str,
    fontsize: str | None = None,
    fontcolor: str | None = None,
    position: str | None = None,
    background: bool = True,
    alpha: float = 1.0,
):
    """Show text overlay on the composited output."""
    elem = _get_overlay("text-overlay")
    if elem is None:
        raise HTTPException(501, "Text overlay not available (engine not running)")

    elem.set_property("silent", False)
    elem.set_property("text", text)

    if fontsize:
        elem.set_property("font-desc", f"Sans Bold {fontsize}")
    if fontcolor:
        # Parse color (hex or named)
        from routes.playout import _parse_text_color

        try:
            color_val = _parse_text_color(fontcolor)
            elem.set_property("color", color_val)
        except Exception:
            pass

    if position:
        position_map = {
            "top-left": ("left", "top"),
            "top-center": ("center", "top"),
            "top-right": ("right", "top"),
            "center": ("center", "center"),
            "bottom-left": ("left", "bottom"),
            "bottom-center": ("center", "bottom"),
            "bottom-right": ("right", "bottom"),
        }
        if position in position_map:
            h, v = position_map[position]
            elem.set_property("halignment", h)
            elem.set_property("valignment", v)

    elem.set_property("shaded-background", background)

    return {"ok": True, "text": text}


@router.delete("/text")
async def clear_text():
    """Clear text overlay."""
    elem = _get_overlay("text-overlay")
    if elem is None:
        raise HTTPException(501, "Text overlay not available")

    elem.set_property("silent", True)
    elem.set_property("text", "")
    return {"ok": True}


@router.post("/bug")
async def show_bug(
    path: str,
    x: int = 0,
    y: int = 0,
    width: int = 0,
    height: int = 0,
    alpha: float = 1.0,
):
    """Show an image bug (channel logo) overlay.

    Args:
        path: Absolute path to a PNG/JPEG image file.
        x: X offset from left (pixels).
        y: Y offset from top (pixels).
        width: Override width (0 = original).
        height: Override height (0 = original).
        alpha: Opacity (0.0-1.0).
    """
    elem = _get_overlay("bug-overlay")
    if elem is None:
        raise HTTPException(
            501, "Bug overlay not available (overlay plugin requires engine restart)"
        )

    elem.set_property("location", path)
    elem.set_property("offset-x", x)
    elem.set_property("offset-y", y)
    if width > 0:
        elem.set_property("overlay-width", width)
    if height > 0:
        elem.set_property("overlay-height", height)
    elem.set_property("alpha", alpha)

    return {"ok": True, "path": path, "x": x, "y": y, "alpha": alpha}


@router.delete("/bug")
async def hide_bug():
    """Hide the image bug overlay."""
    elem = _get_overlay("bug-overlay")
    if elem is None:
        raise HTTPException(501, "Bug overlay not available")

    elem.set_property("alpha", 0.0)
    return {"ok": True}


@router.post("/svg")
async def show_svg(data: str | None = None, path: str | None = None):
    """Show an SVG overlay.

    Provide either inline SVG data or a path to an SVG file.
    """
    elem = _get_overlay("svg-overlay")
    if elem is None:
        raise HTTPException(501, "SVG overlay not available")

    if data:
        elem.set_property("data", data)
    elif path:
        elem.set_property("location", path)
    else:
        raise HTTPException(400, "Provide 'data' (inline SVG) or 'path' (file path)")

    return {"ok": True}


@router.delete("/svg")
async def hide_svg():
    """Hide the SVG overlay."""
    elem = _get_overlay("svg-overlay")
    if elem is None:
        raise HTTPException(501, "SVG overlay not available")

    # Clear by setting empty data
    elem.set_property("data", "")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# Plugin registration
# ══════════════════════════════════════════════════════════════════


class _OverlayPresetStore:
    """Combined preset store for overlay sub-categories (bugs, tickers)."""

    def __init__(self, preset_dir):
        from plugins import FilePresetStore

        self._bugs = FilePresetStore(
            directory=f"{preset_dir}/bugs",
            extension=".json",
            category="bugs",
        )
        self._tickers = FilePresetStore(
            directory=f"{preset_dir}/tickers",
            extension=".json",
            category="tickers",
        )

    def list(self):
        return self._bugs.list() + self._tickers.list()

    def get(self, name):
        return self._bugs.get(name) or self._tickers.get(name)

    def save(self, name, data):
        cat = data.get("category", "bugs")
        store = self._tickers if cat == "tickers" else self._bugs
        return store.save(name, data)

    def delete(self, name):
        return self._bugs.delete(name) or self._tickers.delete(name)


def register(app, config):
    """Register the overlay plugin with cathode."""
    from pathlib import Path

    app.include_router(router)
    preset_dir = str(Path(__file__).parent / "presets")
    presets = _OverlayPresetStore(preset_dir)

    return {
        "category": "graphics",
        "presets": presets,
        "overlay_elements": [
            # (GStreamer factory, element name, default properties)
            (
                "textoverlay",
                "text-overlay",
                {
                    "font-desc": "Sans Bold 24",
                    "silent": True,
                },
            ),
            (
                "gdkpixbufoverlay",
                "bug-overlay",
                {
                    "alpha": 0.0,
                },
            ),
            ("rsvgoverlay", "svg-overlay", {}),
        ],
        "settings": {
            "default_font": {
                "type": "str",
                "value": "Sans Bold 24",
                "description": "Default font for text overlay",
            },
        },
    }
