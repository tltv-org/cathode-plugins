"""gstreamer-source — Native GStreamer pattern/generator sources.

Provides a plugin source type "generator" that builds native GStreamer
source pipelines with configurable patterns and overlays.  No appsrc,
no external process — pure GStreamer elements wired directly into
the InputLayer pipeline.

Source type: "generator"
Category: source,content
System deps: none (uses core GStreamer elements)
Image: works on both cathode:slim and cathode:latest

Live mode usage via API::

    POST /api/playout/layers/input_a/source
    {
        "type": "generator",
        "preset": "smpte-with-tone"
    }

    # Or with inline params:
    POST /api/playout/layers/input_a/source
    {
        "type": "generator",
        "video_pattern": "smpte",
        "audio_wave": "sine",
        "audio_freq": 1000,
        "audio_volume": 0.3,
        "text": "CHANNEL ONE"
    }

Available videotestsrc patterns: smpte, smpte100, snow, black, white,
red, green, blue, checkers-1, checkers-2, checkers-4, checkers-8,
circular, blink, ball, bar, pinwheel, spokes, gradient, colors.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SourceBlockHandler:
    """Schedule block handler that loads a plugin source onto a layer.

    Used to register a source type as a schedule block type. When the
    scheduler activates a block of this type, it loads the source onto
    the target layer via ``load_plugin_source()``.
    """

    def __init__(self, source_type: str):
        self._source_type = source_type

    async def dispatch(self, block: dict, block_key: str, now, ctx) -> None:
        import main

        engine = main.playout
        if engine is None or not engine.is_running:
            raise RuntimeError("Engine not running")

        layer_name = block.get("layer") or "input_a"
        layer = engine.channel(layer_name)

        # Build source config from block fields (exclude schedule metadata)
        config = {
            k: v
            for k, v in block.items()
            if k not in ("type", "start", "end", "title", "layer", "label")
        }

        layer.load_plugin_source(self._source_type, config)
        engine.show(layer_name)


class GeneratorSourceFactory:
    """Builds native GStreamer source pipelines on an InputLayer.

    Pipeline::

        videotestsrc(pattern, is-live) → [textoverlay] → vnorm → queue → intervideosink
        audiotestsrc(wave, freq, volume, is-live) → acaps → queue → interaudiosink

    Presets are JSON files that define source element properties and
    optional text overlays.
    """

    def __init__(self, preset_dir: str = "/config/generator-presets"):
        self._preset_dir = preset_dir
        self._presets: dict[str, dict] = {}
        self._load_presets()

    def _load_presets(self) -> None:
        """Load JSON preset files from the preset directory."""
        pdir = Path(self._preset_dir)
        if not pdir.exists():
            return
        for path in sorted(pdir.glob("*.json")):
            try:
                with open(path) as f:
                    preset = json.load(f)
                preset.setdefault("name", path.stem)
                self._presets[path.stem] = preset
            except Exception as exc:
                logger.warning("Failed to load preset %s: %s", path, exc)
        if self._presets:
            logger.info("Loaded %d generator presets", len(self._presets))

    def build(self, layer, config: dict) -> None:
        """Build a GStreamer source pipeline on the given InputLayer.

        Args:
            layer: InputLayer instance.
            config: Source config dict.  Fields:
                - preset: Name of a saved preset (loads from JSON)
                - video_pattern: videotestsrc pattern (default: "smpte")
                - audio_wave: audiotestsrc wave name or int (default: 4/silence)
                - audio_freq: audiotestsrc frequency Hz (default: 1000)
                - audio_volume: audiotestsrc volume 0.0-1.0 (default: 0.1)
                - text: optional text overlay string
                - text_font: font description (default: "Sans Bold 36")
        """
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        # If a preset is specified, merge its values with config
        preset_name = config.get("preset")
        if preset_name:
            preset = self._presets.get(preset_name)
            if preset is None:
                available = list(self._presets.keys())
                raise ValueError(
                    f"Generator preset '{preset_name}' not found. "
                    f"Available: {available}"
                )
            # Preset values are defaults; explicit config overrides
            merged = {**preset, **{k: v for k, v in config.items() if v is not None}}
        else:
            merged = config

        prefix = f"ch{layer.index}_gen"
        cfg = layer._config

        video_pattern = merged.get("video_pattern", "smpte")
        audio_wave = merged.get("audio_wave", 4)  # silence
        audio_freq = merged.get("audio_freq", 1000)
        audio_volume = merged.get("audio_volume", 0.1)
        text = merged.get("text")
        text_font = merged.get("text_font", "Sans Bold 36")

        # Map wave names to integers
        wave_map = {
            "sine": 0,
            "square": 1,
            "saw": 2,
            "triangle": 3,
            "silence": 4,
            "white-noise": 5,
            "pink-noise": 6,
            "ticks": 8,
        }
        if isinstance(audio_wave, str):
            audio_wave = wave_map.get(audio_wave, 4)

        # ── Video source ──
        vsrc = Gst.ElementFactory.make("videotestsrc", f"{prefix}_vsrc")
        vsrc.set_property("is-live", True)
        vsrc.set_property("pattern", video_pattern)

        elements = [vsrc]

        # Optional text overlay
        if text:
            overlay = Gst.ElementFactory.make("textoverlay", f"{prefix}_text")
            overlay.set_property("text", text)
            overlay.set_property("font-desc", text_font)
            overlay.set_property("halignment", "center")
            overlay.set_property("valignment", "center")
            overlay.set_property("shaded-background", True)
            elements.append(overlay)

        # Video normalize + queue
        vconv = Gst.ElementFactory.make("videoconvert", f"{prefix}_vconv")
        vscale = Gst.ElementFactory.make("videoscale", f"{prefix}_vscale")
        vrate = Gst.ElementFactory.make("videorate", f"{prefix}_vrate")
        vcaps = Gst.ElementFactory.make("capsfilter", f"{prefix}_vcaps")
        vcaps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,width={cfg.width},height={cfg.height},"
                f"framerate={cfg.fps}/1,format=I420"
            ),
        )
        vq = Gst.ElementFactory.make("queue", f"{prefix}_vq")
        vq.set_property("max-size-time", 2 * Gst.SECOND)

        elements.extend([vconv, vscale, vrate, vcaps, vq])

        # ── Audio source ──
        asrc = Gst.ElementFactory.make("audiotestsrc", f"{prefix}_asrc")
        asrc.set_property("is-live", True)
        asrc.set_property("wave", audio_wave)
        asrc.set_property("freq", audio_freq)
        asrc.set_property("volume", audio_volume)

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

        elements.extend([asrc, acaps, aq])

        # ── Add all elements ──
        for elem in elements:
            layer._pipeline.add(elem)
        layer._source_elements = elements

        # ── Link video chain ──
        prev = vsrc
        for elem in elements[1:]:  # skip vsrc, link sequentially until aq
            if elem in (asrc, acaps, aq):
                break
            prev.link(elem)
            prev = elem

        # ── Link audio chain ──
        asrc.link(acaps)
        acaps.link(aq)

        # ── Link to inter sinks ──
        layer._link_to_output(
            vq.get_static_pad("src"),
            aq.get_static_pad("src"),
        )

        logger.info(
            "gstreamer-source factory: built pipeline "
            "(pattern=%s, wave=%s, text=%s, %dx%d@%dfps)",
            video_pattern,
            audio_wave,
            text[:30] if text else None,
            cfg.width,
            cfg.height,
            cfg.fps,
        )


async def _generate(config: dict, presets: dict) -> dict:
    """Generate a media file using a standalone GStreamer pipeline.

    Builds the same source elements as live mode but pipes to
    x264enc + avenc_aac + mp4mux + filesink instead of inter sinks.
    Runs for the specified duration, then sends EOS.
    """
    import asyncio
    import time

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    Gst.init(None)

    preset_name = config.get("preset")
    duration = config.get("duration", 30)
    width = config.get("width", 1920)
    height = config.get("height", 1080)
    fps = config.get("fps", 30)
    media_dir = config.get("media_dir", "/media")
    filename = (
        config.get("filename")
        or f"gen-{preset_name or 'custom'}-{int(time.time())}.mp4"
    )
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    output_path = os.path.join(media_dir, filename)

    # Resolve params from preset
    merged = dict(config)
    if preset_name and preset_name in presets:
        merged = {
            **presets[preset_name],
            **{k: v for k, v in config.items() if v is not None},
        }

    video_pattern = merged.get("video_pattern", "smpte")
    audio_wave = merged.get("audio_wave", 4)
    audio_freq = merged.get("audio_freq", 1000)
    audio_volume = merged.get("audio_volume", 0.1)
    text = merged.get("text")
    text_font = merged.get("text_font", "Sans Bold 36")

    wave_map = {
        "sine": 0,
        "square": 1,
        "saw": 2,
        "triangle": 3,
        "silence": 4,
        "white-noise": 5,
        "pink-noise": 6,
        "ticks": 8,
    }
    if isinstance(audio_wave, str):
        audio_wave = wave_map.get(audio_wave, 4)

    num_buffers = duration * fps

    # ── Build standalone pipeline ──
    pipeline = Gst.Pipeline.new("generate")

    # Video source
    vsrc = Gst.ElementFactory.make("videotestsrc", "vsrc")
    vsrc.set_property("pattern", video_pattern)
    vsrc.set_property("num-buffers", num_buffers)

    vconv = Gst.ElementFactory.make("videoconvert", "vconv")
    vcaps = Gst.ElementFactory.make("capsfilter", "vcaps")
    vcaps.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw,width={width},height={height},framerate={fps}/1,format=I420"
        ),
    )

    v_elements = [vsrc]
    if text:
        overlay = Gst.ElementFactory.make("textoverlay", "text")
        overlay.set_property("text", text)
        overlay.set_property("font-desc", text_font)
        overlay.set_property("halignment", "center")
        overlay.set_property("valignment", "center")
        overlay.set_property("shaded-background", True)
        v_elements.append(overlay)
    v_elements.extend([vconv, vcaps])

    x264 = Gst.ElementFactory.make("x264enc", "venc")
    x264.set_property("tune", "zerolatency")
    x264.set_property("speed-preset", "ultrafast")
    x264.set_property("bitrate", 4000)
    v_elements.append(x264)

    # Audio source
    asrc = Gst.ElementFactory.make("audiotestsrc", "asrc")
    asrc.set_property("wave", audio_wave)
    asrc.set_property("freq", audio_freq)
    asrc.set_property("volume", audio_volume)
    asrc.set_property(
        "num-buffers", int(duration * 48000 / 1024)
    )  # ~48kHz / buffer size

    aconv = Gst.ElementFactory.make("audioconvert", "aconv")
    aenc = Gst.ElementFactory.make("avenc_aac", "aenc")

    # Mux + sink
    mux = Gst.ElementFactory.make("mp4mux", "mux")
    sink = Gst.ElementFactory.make("filesink", "sink")
    sink.set_property("location", output_path)

    # Add all elements
    all_elements = v_elements + [asrc, aconv, aenc, mux, sink]
    for elem in all_elements:
        pipeline.add(elem)

    # Link video chain → mux
    prev = v_elements[0]
    for elem in v_elements[1:]:
        prev.link(elem)
        prev = elem
    x264.link(mux)

    # Link audio chain → mux
    asrc.link(aconv)
    aconv.link(aenc)
    aenc.link(mux)

    # Link mux → sink
    mux.link(sink)

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

    pipeline.set_state(Gst.State.PLAYING)

    # Run in a thread so we don't block the asyncio event loop
    def _run():
        loop.run()
        pipeline.set_state(Gst.State.NULL)

    await asyncio.get_running_loop().run_in_executor(None, _run)

    if error_msg:
        raise RuntimeError(f"GStreamer pipeline error: {error_msg}")

    logger.info("Generated: %s (%ds)", filename, duration)
    return {"filename": filename, "path": output_path, "duration": duration}


def register(app, config):
    """Register the gstreamer-source plugin with cathode."""
    from plugins import FilePresetStore

    preset_dir = os.environ.get("GENERATOR_PRESET_DIR", "/config/generator-presets")
    # Also check the plugin's own presets directory
    plugin_dir = Path(__file__).parent / "presets"
    effective_dir = preset_dir if os.path.isdir(preset_dir) else str(plugin_dir)

    factory = GeneratorSourceFactory(preset_dir=effective_dir)

    # Preset provider for the /api/plugins/gstreamer-source/presets endpoint
    presets = FilePresetStore(directory=effective_dir, extension=".json")

    # Wrap generate to inject loaded presets
    async def generate_with_presets(cfg: dict) -> dict:
        return await _generate(cfg, factory._presets)

    return {
        "category": "source,content",
        "services": {
            "generator_factory": factory,
        },
        "source_types": {
            "generator": {
                "factory": factory,
                "description": "Native GStreamer pattern/generator sources",
                "params": {
                    "preset": {
                        "type": "str",
                        "description": "Name of a saved JSON preset",
                    },
                    "video_pattern": {
                        "type": "str",
                        "description": "videotestsrc pattern (smpte, snow, etc.)",
                        "default": "smpte",
                    },
                    "audio_wave": {
                        "type": "str",
                        "description": "Audio wave (sine, silence, white-noise, etc.)",
                        "default": "silence",
                    },
                    "audio_freq": {
                        "type": "int",
                        "description": "Audio frequency in Hz",
                        "default": 1000,
                    },
                    "audio_volume": {
                        "type": "float",
                        "description": "Audio volume 0.0-1.0",
                        "default": 0.1,
                    },
                    "text": {
                        "type": "str",
                        "description": "Optional text overlay",
                    },
                    "text_font": {
                        "type": "str",
                        "description": "Font description for text overlay",
                        "default": "Sans Bold 36",
                    },
                },
            },
        },
        "block_types": {
            "generator": {
                "handler": SourceBlockHandler("generator"),
                "description": "Native GStreamer pattern/generator sources",
                "params": {
                    "preset": {
                        "type": "str",
                        "description": "Name of a saved JSON preset",
                    },
                    "video_pattern": {
                        "type": "str",
                        "description": "videotestsrc pattern",
                    },
                    "audio_wave": {"type": "str", "description": "Audio wave type"},
                    "audio_freq": {"type": "int", "description": "Audio frequency Hz"},
                    "audio_volume": {
                        "type": "float",
                        "description": "Audio volume 0.0-1.0",
                    },
                    "text": {"type": "str", "description": "Optional text overlay"},
                    "layer": {
                        "type": "str",
                        "description": "Target layer (default: input_a)",
                    },
                },
            },
        },
        "presets": presets,
        "generate": generate_with_presets,
        "settings": {
            "preset_dir": {
                "type": "str",
                "value": effective_dir,
                "description": "Directory for generator presets (JSON)",
            },
        },
    }
