"""html-source — HTML/CSS/JS rendering via WPE WebKit.

Provides a plugin source type "html" that uses GStreamer's wpesrc
element to render HTML pages directly into video frames.  No sidecar
container, no intermediate transport — wpesrc is a native GStreamer
source that embeds a WPE WebKit renderer.

Source type: "html"
Category: source
System deps: gstreamer1.0-wpe, libgles2, libegl1, libegl-mesa0, libgl1-mesa-dri
Image: requires cathode:latest (full)

Usage via API::

    POST /api/playout/layers/input_a/source
    {
        "type": "html",
        "location": "file:///data/html-presets/intro.html",
        "fps": 30
    }

    # Or with inline HTML via load-bytes (no temp file):
    POST /api/playout/layers/input_a/source
    {
        "type": "html",
        "html": "<html><body style='background:#000'><h1>Hello</h1></body></html>"
    }

Features verified in Phase 0:
- file:// and https:// URLs
- Inline HTML via GLib.Bytes load-bytes action
- Runtime JavaScript injection via run-javascript action
- CSS animations (keyframes, transitions)
- Canvas 2D API
- JavaScript timers (setInterval, requestAnimationFrame)
- ~230% CPU / ~620MB RAM at 1080p30 with software rendering
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class SourceBlockHandler:
    """Schedule block handler that loads a plugin source onto a layer."""

    def __init__(self, source_type: str):
        self._source_type = source_type

    async def dispatch(self, block: dict, block_key: str, now, ctx) -> None:
        import main

        engine = main.playout
        if engine is None or not engine.is_running:
            raise RuntimeError("Engine not running")

        layer_name = block.get("layer") or "input_a"
        layer = engine.channel(layer_name)

        config = {
            k: v
            for k, v in block.items()
            if k not in ("type", "start", "end", "title", "layer", "label")
        }

        layer.load_plugin_source(self._source_type, config)
        engine.show(layer_name)


class HTMLSourceFactory:
    """Builds a wpesrc GStreamer pipeline on an InputLayer.

    Called by InputLayer.load_plugin_source("html", config) when the
    engine needs to load an HTML source on a layer.

    The factory creates GStreamer elements, adds them to the layer's
    pipeline, and links to the inter sinks.  The InputLayer handles
    all lifecycle (teardown, start, error handling, failover).
    """

    def __init__(self, preset_dir: str = ""):
        self._preset_dir = preset_dir

    def build(self, layer, config: dict) -> None:
        """Build the wpesrc pipeline on the given InputLayer.

        Args:
            layer: InputLayer instance.  Provides:
                - layer._pipeline: GstPipeline to add elements to
                - layer._v_sink / layer._a_sink: inter sinks to link to
                - layer._config: MixerConfig (width, height, fps, audio)
                - layer._link_to_output(v_pad, a_pad): helper to link
                - layer._source_elements: list to store elements for teardown
                - layer.index: channel index for naming
            config: Source config dict from the API request.  Fields:
                - location: URL to render (file://, https://, about:blank)
                - html: Inline HTML string (alternative to location)
                - fps: Override framerate (default: from mixer config)
                - draw_background: Whether to draw page background (default: True)
        """
        from pathlib import Path

        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst, GLib

        prefix = f"ch{layer.index}_html"
        cfg = layer._config
        fps = config.get("fps", cfg.fps)
        location = config.get("location")
        html_content = config.get("html")
        draw_bg = config.get("draw_background", True)

        # Resolve preset name to file:// location (or inline HTML if params
        # are provided, so {{KEY}} template variables get substituted).
        preset_name = config.get("preset")
        params = config.get("params") or {}
        if preset_name and not location and not html_content:
            preset_path = Path(self._preset_dir) / f"{preset_name}.html"
            if not preset_path.exists():
                # Try without extension
                preset_path = Path(self._preset_dir) / preset_name
            if not preset_path.exists():
                available = [p.stem for p in Path(self._preset_dir).glob("*.html")]
                raise ValueError(
                    f"HTML preset '{preset_name}' not found. Available: {available}"
                )
            if params:
                # Read HTML, substitute {{KEY}} with param values, push
                # as inline HTML so the template variables are resolved.
                raw = preset_path.read_text(encoding="utf-8")
                for key, value in params.items():
                    raw = raw.replace("{{" + key + "}}", str(value))
                html_content = raw
                logger.debug(
                    "html-source: substituted %d params into preset %s",
                    len(params),
                    preset_name,
                )
            else:
                location = f"file://{preset_path}"

        if not location and not html_content:
            location = "about:blank"

        # ── wpesrc (video) ──
        wpesrc = Gst.ElementFactory.make("wpesrc", f"{prefix}_wpe")
        if wpesrc is None:
            raise RuntimeError(
                "GStreamer element 'wpesrc' not found. "
                "Install gstreamer1.0-wpe (cathode:latest image)."
            )

        if not html_content:
            wpesrc.set_property("location", location)
        wpesrc.set_property("draw-background", draw_bg)

        # Video normalize: wpesrc outputs BGRA → convert to I420
        vconv = Gst.ElementFactory.make("videoconvert", f"{prefix}_vconv")
        vscale = Gst.ElementFactory.make("videoscale", f"{prefix}_vscale")
        vcaps = Gst.ElementFactory.make("capsfilter", f"{prefix}_vcaps")
        vcaps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,width={cfg.width},height={cfg.height},"
                f"framerate={fps}/1,format=I420"
            ),
        )
        vq = Gst.ElementFactory.make("queue", f"{prefix}_vq")
        vq.set_property("max-size-time", 2 * Gst.SECOND)

        # ── Silent audio (HTML pages with <audio> get audio pads
        #    dynamically, but most pages are silent) ──
        asrc = Gst.ElementFactory.make("audiotestsrc", f"{prefix}_asrc")
        asrc.set_property("is-live", True)
        asrc.set_property("wave", 4)  # silence
        acaps = Gst.ElementFactory.make("capsfilter", f"{prefix}_acaps")
        acaps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"audio/x-raw,rate={cfg.audio_samplerate},"
                f"channels={cfg.audio_channels},"
                f"format=F32LE,layout=interleaved"
            ),
        )
        aq = Gst.ElementFactory.make("queue", f"{prefix}_aq")

        # ── Add all elements to the layer's pipeline ──
        elements = [wpesrc, vconv, vscale, vcaps, vq, asrc, acaps, aq]
        for elem in elements:
            layer._pipeline.add(elem)
        layer._source_elements = elements

        # Store wpesrc reference for runtime JS injection / load-bytes
        layer._wpesrc = wpesrc

        # ── Link video chain ──
        wpesrc.link(vconv)
        vconv.link(vscale)
        vscale.link(vcaps)
        vcaps.link(vq)

        # ── Link audio chain ──
        asrc.link(acaps)
        acaps.link(aq)

        # ── Link to inter sinks ──
        layer._link_to_output(
            vq.get_static_pad("src"),
            aq.get_static_pad("src"),
        )

        # ── If inline HTML provided, push it via load-bytes after start ──
        if html_content:

            def _push_html(*args, src=wpesrc, html=html_content):
                """Push inline HTML via load-bytes on state change to PLAYING."""
                gbytes = GLib.Bytes.new(html.encode("utf-8"))
                src.emit("load-bytes", gbytes)
                # Disconnect after first fire
                return False

            # Push HTML after pipeline reaches PLAYING
            # Use a pad probe on the video output to trigger after first buffer
            def _on_buffer(pad, info, src=wpesrc, html=html_content):
                gbytes = GLib.Bytes.new(html.encode("utf-8"))
                src.emit("load-bytes", gbytes)
                return Gst.PadProbeReturn.REMOVE  # one-shot

            # Set initial location to about:blank, then push real content
            wpesrc.set_property("location", "about:blank")
            vq.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, _on_buffer)

        logger.info(
            "html-source factory: built wpesrc pipeline (location=%s, %dx%d@%dfps)",
            location if not html_content else "(inline HTML)",
            cfg.width,
            cfg.height,
            fps,
        )


async def _generate(config: dict) -> dict:
    """Generate a media file by rendering HTML via wpesrc to file.

    Builds: wpesrc → videoconvert → x264enc + avenc_aac → mp4mux → filesink.
    Same source as live mode, different output end.
    """
    import asyncio
    import os
    import time

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    Gst.init(None)

    duration = config.get("duration", 30)
    width = config.get("width", 1920)
    height = config.get("height", 1080)
    fps = config.get("fps", 30)
    media_dir = config.get("media_dir", "/media")
    preset_name = config.get("preset")
    location = config.get("location")
    html_content = config.get("html")
    draw_bg = config.get("draw_background", True)

    # Resolve preset to location if specified (with param substitution)
    preset_dir = config.get("_preset_dir")
    params = config.get("params") or {}
    if preset_name and preset_dir:
        from pathlib import Path

        preset_path = Path(preset_dir) / f"{preset_name}.html"
        if not preset_path.exists():
            available = [p.stem for p in Path(preset_dir).glob("*.html")]
            raise ValueError(
                f"HTML preset '{preset_name}' not found. Available: {available}"
            )
        if params:
            raw = preset_path.read_text(encoding="utf-8")
            for key, value in params.items():
                raw = raw.replace("{{" + key + "}}", str(value))
            html_content = raw
        else:
            location = f"file://{preset_path}"

    if not location and not html_content:
        raise ValueError("Either 'preset', 'location', or 'html' is required")

    filename = (
        config.get("filename")
        or f"html-{preset_name or 'render'}-{int(time.time())}.mp4"
    )
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    output_path = os.path.join(media_dir, filename)

    num_buffers = duration * fps

    # ── Build standalone pipeline ──
    pipeline = Gst.Pipeline.new("html-generate")

    # Video: wpesrc → videoconvert → x264enc
    wpesrc = Gst.ElementFactory.make("wpesrc", "wpe")
    if wpesrc is None:
        raise RuntimeError("wpesrc not found. Requires cathode:latest (full) image.")
    if not html_content:
        wpesrc.set_property("location", location)
    wpesrc.set_property("draw-background", draw_bg)

    vconv = Gst.ElementFactory.make("videoconvert", "vconv")
    vscale = Gst.ElementFactory.make("videoscale", "vscale")
    vcaps = Gst.ElementFactory.make("capsfilter", "vcaps")
    vcaps.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw,width={width},height={height},framerate={fps}/1,format=I420"
        ),
    )
    x264 = Gst.ElementFactory.make("x264enc", "venc")
    x264.set_property("tune", "zerolatency")
    x264.set_property("speed-preset", "ultrafast")
    x264.set_property("bitrate", 4000)

    # Audio: silent source
    asrc = Gst.ElementFactory.make("audiotestsrc", "asrc")
    asrc.set_property("wave", 4)  # silence
    asrc.set_property("num-buffers", int(duration * 48000 / 1024))
    aconv = Gst.ElementFactory.make("audioconvert", "aconv")
    aenc = Gst.ElementFactory.make("avenc_aac", "aenc")

    # Mux + sink
    mux = Gst.ElementFactory.make("mp4mux", "mux")
    sink = Gst.ElementFactory.make("filesink", "sink")
    sink.set_property("location", output_path)

    for elem in [wpesrc, vconv, vscale, vcaps, x264, asrc, aconv, aenc, mux, sink]:
        pipeline.add(elem)

    wpesrc.link(vconv)
    vconv.link(vscale)
    vscale.link(vcaps)
    vcaps.link(x264)
    x264.link(mux)
    asrc.link(aconv)
    aconv.link(aenc)
    aenc.link(mux)
    mux.link(sink)

    # ── Inline HTML: push via load-bytes after pipeline starts ──
    if html_content:
        wpesrc.set_property("location", "about:blank")

        def _on_buffer(pad, info):
            gbytes = GLib.Bytes.new(html_content.encode("utf-8"))
            wpesrc.emit("load-bytes", gbytes)
            return Gst.PadProbeReturn.REMOVE

        vcaps.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, _on_buffer)

    # ── Run pipeline ──
    loop = GLib.MainLoop.new(None, False)
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    error_msg = None

    def _on_message(bus, msg):
        nonlocal error_msg
        if msg.type == Gst.MessageType.EOS:
            loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            error_msg = f"{err.message}: {debug}"
            loop.quit()

    bus.connect("message", _on_message)

    # Send EOS after duration
    def _send_eos():
        pipeline.send_event(Gst.Event.new_eos())
        return False  # don't repeat

    GLib.timeout_add(duration * 1000, _send_eos)

    pipeline.set_state(Gst.State.PLAYING)

    def _run():
        loop.run()
        pipeline.set_state(Gst.State.NULL)

    await asyncio.get_running_loop().run_in_executor(None, _run)

    if error_msg:
        raise RuntimeError(f"GStreamer pipeline error: {error_msg}")

    logger.info("Generated: %s (%ds)", filename, duration)
    return {"filename": filename, "path": output_path, "duration": duration}


def register(app, config):
    """Register the html-source plugin with cathode."""
    from pathlib import Path

    from plugins import FilePresetStore

    plugin_dir = Path(__file__).parent / "presets"
    presets = FilePresetStore(directory=str(plugin_dir), extension=".html")

    async def generate_with_presets(cfg: dict) -> dict:
        cfg["_preset_dir"] = str(plugin_dir)
        return await _generate(cfg)

    return {
        "category": "source,content",
        "presets": presets,
        "generate": generate_with_presets,
        "block_types": {
            "html": {
                "handler": SourceBlockHandler("html"),
                "description": "HTML/CSS/JS rendering via WPE WebKit",
                "params": {
                    "location": {
                        "type": "str",
                        "description": "URL to render (file://, https://)",
                    },
                    "html": {"type": "str", "description": "Inline HTML content"},
                    "fps": {"type": "int", "description": "Override framerate"},
                    "draw_background": {
                        "type": "bool",
                        "description": "Draw page background",
                        "default": True,
                    },
                    "layer": {
                        "type": "str",
                        "description": "Target layer (default: input_a)",
                    },
                },
            },
        },
        "source_types": {
            "html": {
                "factory": HTMLSourceFactory(preset_dir=str(plugin_dir)),
                "description": "HTML/CSS/JS rendering via WPE WebKit",
                "params": {
                    "location": {
                        "type": "str",
                        "description": "URL to render (file://, https://, about:blank)",
                    },
                    "html": {
                        "type": "str",
                        "description": "Inline HTML content (alternative to location)",
                    },
                    "fps": {
                        "type": "int",
                        "description": "Override framerate (default: from mixer config)",
                    },
                    "draw_background": {
                        "type": "bool",
                        "description": "Whether to draw the page background",
                        "default": True,
                    },
                    "params": {
                        "type": "dict",
                        "description": "Template parameters — substitutes {{KEY}} in preset HTML",
                    },
                },
            },
        },
        "system_deps": [
            "gstreamer1.0-wpe",
            "libgles2",
            "libegl1",
            "libegl-mesa0",
            "libgl1-mesa-dri",
        ],
    }
