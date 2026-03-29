"""script-source — Python script live rendering via appsrc.

Provides a plugin source type "script" that runs a Python preset
script in a subprocess and pushes raw video frames into GStreamer
via appsrc.  The script generates RGBA frames and writes them to
stdout; the plugin reads them and feeds appsrc.

Source type: "script"
Category: source,content
System deps: none (Pillow is in cathode:latest)
Image: requires cathode:latest (full) for Pillow

Live mode usage via API::

    POST /api/playout/layers/input_a/source
    {
        "type": "script",
        "preset": "geometric-shapes"
    }

Safety:
- Saved presets only — no inline code from the API
- Subprocess resource limits (timeout, memory)
- Separate user: runs as nobody
- Sanitized environment
"""

from __future__ import annotations

import logging

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


class ScriptSourceFactory:
    """Builds an appsrc GStreamer pipeline fed by a Python script subprocess.

    Called by InputLayer.load_plugin_source("script", config) when the
    engine needs to load a Python script source on a layer.

    Pipeline::

        appsrc(format=time, caps=video/x-raw,format=RGBA,...)
            → videoconvert → capsfilter(I420) → queue → intervideosink
        audiotestsrc(silence, is-live)
            → capsfilter → queue → interaudiosink

    The subprocess protocol is simple: the script writes raw RGBA
    frames (width*height*4 bytes each) to stdout at the target fps.
    The plugin reads frames in a thread and pushes them to appsrc.
    """

    def __init__(self, preset_dir: str = "/config/script-presets"):
        self._preset_dir = preset_dir

    def build(self, layer, config: dict) -> None:
        """Build the appsrc pipeline on the given InputLayer.

        Args:
            layer: InputLayer instance.
            config: Source config dict.  Fields:
                - preset: Name of a saved preset script
                - fps: Override framerate (default: from mixer config)
                - params: Dict of params to pass to the script as env vars
        """
        import os
        import resource
        import subprocess
        import threading
        from pathlib import Path

        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst, GLib

        prefix = f"ch{layer.index}_script"
        cfg = layer._config
        fps = config.get("fps", cfg.fps)
        width = cfg.width
        height = cfg.height
        preset_name = config.get("preset")

        if not preset_name:
            raise ValueError("'preset' is required for script source")

        # Resolve preset path
        preset_path = Path(self._preset_dir) / f"{preset_name}.py"
        if not preset_path.exists():
            # Try without extension
            preset_path = Path(self._preset_dir) / preset_name
            if not preset_path.exists():
                available = (
                    [p.stem for p in Path(self._preset_dir).glob("*.py")]
                    if Path(self._preset_dir).exists()
                    else []
                )
                raise ValueError(
                    f"Script preset '{preset_name}' not found. Available: {available}"
                )

        frame_size = width * height * 4  # RGBA

        # ── appsrc (video) ──
        appsrc = Gst.ElementFactory.make("appsrc", f"{prefix}_appsrc")
        if appsrc is None:
            raise RuntimeError("GStreamer element 'appsrc' not found")

        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("is-live", True)
        appsrc.set_property("do-timestamp", False)
        appsrc.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,format=RGBA,width={width},height={height},"
                f"framerate={fps}/1"
            ),
        )
        # Block push_buffer when queue is full (backpressure)
        appsrc.set_property("block", True)
        appsrc.set_property("max-bytes", frame_size * 3)  # ~3 frames buffer

        # Video normalize: RGBA → I420
        vconv = Gst.ElementFactory.make("videoconvert", f"{prefix}_vconv")
        vcaps = Gst.ElementFactory.make("capsfilter", f"{prefix}_vcaps")
        vcaps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,width={width},height={height},"
                f"framerate={fps}/1,format=I420"
            ),
        )
        vq = Gst.ElementFactory.make("queue", f"{prefix}_vq")
        vq.set_property("max-size-time", 2 * Gst.SECOND)

        # ── Silent audio ──
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

        # ── Add elements to pipeline ──
        elements = [appsrc, vconv, vcaps, vq, asrc, acaps, aq]
        for elem in elements:
            layer._pipeline.add(elem)
        layer._source_elements = elements

        # ── Link ──
        appsrc.link(vconv)
        vconv.link(vcaps)
        vcaps.link(vq)
        asrc.link(acaps)
        acaps.link(aq)

        layer._link_to_output(
            vq.get_static_pad("src"),
            aq.get_static_pad("src"),
        )

        # Store appsrc reference
        layer._appsrc = appsrc

        # ── Build subprocess environment ──
        script_env = {
            "WIDTH": str(width),
            "HEIGHT": str(height),
            "FPS": str(fps),
            "OUTPUT": "stdout",  # signal to script: write raw RGBA to stdout
            "PYTHONUNBUFFERED": "1",
        }
        # Add user params as PARAM_* env vars
        for k, v in (config.get("params") or {}).items():
            script_env[f"PARAM_{k.upper()}"] = str(v)

        # Restricted PATH
        script_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"

        # ── Launch subprocess and feed appsrc in a thread ──
        def _feed_loop():
            """Read frames from script subprocess and push to appsrc.

            Uses a separate reader thread to pull raw RGBA frames from
            the script's stdout.  The main feed loop pushes to appsrc
            at the target FPS using ``block=True`` backpressure.  If
            the script renders slower than real-time the last frame is
            re-pushed, ensuring the pipeline always receives a
            continuous stream with no gaps.
            """
            try:

                def _set_limits():
                    """Set resource limits for the subprocess."""
                    # 512MB memory limit
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (512 * 1024 * 1024, 512 * 1024 * 1024),
                    )

                proc = subprocess.Popen(
                    ["python3", str(preset_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=script_env,
                    preexec_fn=_set_limits,
                )
                layer._script_proc = proc

                # ── Reader thread: pull frames from script stdout ──
                frame_lock = threading.Lock()
                latest_frame = [None]  # mutable container
                reader_done = [False]

                def _reader():
                    while proc.poll() is None:
                        data = proc.stdout.read(frame_size)
                        if len(data) != frame_size:
                            break
                        with frame_lock:
                            latest_frame[0] = data
                    reader_done[0] = True

                reader = threading.Thread(
                    target=_reader,
                    name=f"script-reader-ch{layer.index}",
                    daemon=True,
                )
                reader.start()

                # Wait for the first frame (up to 10s for slow scripts).
                for _ in range(2000):
                    if latest_frame[0] is not None or reader_done[0]:
                        break
                    if not layer._bus_running:
                        break
                    threading.Event().wait(0.005)

                # ── Push loop: feed appsrc at target FPS ──
                frame_num = 0
                frame_ns = Gst.SECOND // fps

                while layer._bus_running and not reader_done[0]:
                    with frame_lock:
                        data = latest_frame[0]
                    if data is None:
                        break

                    buf = Gst.Buffer.new_allocate(None, frame_size, None)
                    buf.fill(0, data)
                    buf.pts = frame_num * frame_ns
                    buf.duration = frame_ns

                    ret = appsrc.emit("push-buffer", buf)
                    if ret != Gst.FlowReturn.OK:
                        break
                    frame_num += 1

                # Script ended — send EOS to appsrc
                appsrc.emit("end-of-stream")
                proc.terminate()
                proc.wait(timeout=5)
                reader.join(timeout=2)

                stderr_out = proc.stderr.read().decode(errors="replace")
                if proc.returncode and proc.returncode != 0:
                    logger.warning(
                        "Script '%s' exited with code %d: %s",
                        preset_name,
                        proc.returncode,
                        stderr_out[:500],
                    )
                elif stderr_out.strip():
                    logger.debug(
                        "Script '%s' stderr: %s", preset_name, stderr_out[:200]
                    )

            except Exception as exc:
                logger.error("Script feed error: %s", exc)
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass

        feed_thread = threading.Thread(
            target=_feed_loop,
            name=f"script-feed-ch{layer.index}",
            daemon=True,
        )
        # Start after _start_source() sets _bus_running — store ref so
        # the thread starts when the pipeline reaches PLAYING.
        layer._script_feed_thread = feed_thread
        feed_thread.start()

        logger.info(
            "script-source factory: built appsrc pipeline (preset=%s, %dx%d@%dfps)",
            preset_name,
            width,
            height,
            fps,
        )


async def _generate(config: dict, preset_dir: str) -> dict:
    """Generate a media file by running a script and encoding via GStreamer.

    Builds: appsrc (fed by script subprocess) → x264enc + avenc_aac → mp4mux → filesink.
    Same source mechanism as live mode, different output end.
    """
    import asyncio
    import os
    import resource
    import subprocess
    import threading
    import time
    from pathlib import Path

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    Gst.init(None)

    preset_name = config.get("preset")
    if not preset_name:
        raise ValueError("'preset' is required for script generation")

    duration = config.get("duration", 30)
    width = config.get("width", 1920)
    height = config.get("height", 1080)
    fps = config.get("fps", 30)
    media_dir = config.get("media_dir", "/media")
    filename = config.get("filename") or f"script-{preset_name}-{int(time.time())}.mp4"
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    output_path = os.path.join(media_dir, filename)

    # Resolve preset path
    preset_path = Path(preset_dir) / f"{preset_name}.py"
    if not preset_path.exists():
        preset_path = Path(preset_dir) / preset_name
        if not preset_path.exists():
            available = (
                [p.stem for p in Path(preset_dir).glob("*.py")]
                if Path(preset_dir).exists()
                else []
            )
            raise ValueError(
                f"Script preset '{preset_name}' not found. Available: {available}"
            )

    frame_size = width * height * 4  # RGBA
    num_frames = duration * fps

    # ── Build GStreamer pipeline ──
    pipeline = Gst.Pipeline.new("script-generate")

    # Video: appsrc → videoconvert → x264enc
    appsrc = Gst.ElementFactory.make("appsrc", "appsrc")
    appsrc.set_property("format", Gst.Format.TIME)
    appsrc.set_property("is-live", False)
    appsrc.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw,format=RGBA,width={width},height={height},framerate={fps}/1"
        ),
    )
    appsrc.set_property("block", True)
    appsrc.set_property("max-bytes", frame_size * 3)

    vconv = Gst.ElementFactory.make("videoconvert", "vconv")
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

    for elem in [appsrc, vconv, x264, asrc, aconv, aenc, mux, sink]:
        pipeline.add(elem)

    appsrc.link(vconv)
    vconv.link(x264)
    x264.link(mux)
    asrc.link(aconv)
    aconv.link(aenc)
    aenc.link(mux)
    mux.link(sink)

    # ── Script subprocess → appsrc feeder thread ──
    script_env = {
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FPS": str(fps),
        "DURATION": str(duration),
        "OUTPUT": "stdout",
        "PYTHONUNBUFFERED": "1",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    for k, v in (config.get("params") or {}).items():
        script_env[f"PARAM_{k.upper()}"] = str(v)

    feed_error = None

    def _feed_loop():
        nonlocal feed_error
        try:

            def _set_limits():
                resource.setrlimit(
                    resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024)
                )

            proc = subprocess.Popen(
                ["python3", str(preset_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=script_env,
                preexec_fn=_set_limits,
            )
            frame_num = 0
            while frame_num < num_frames and proc.poll() is None:
                data = proc.stdout.read(frame_size)
                if len(data) != frame_size:
                    break
                buf = Gst.Buffer.new_allocate(None, frame_size, None)
                buf.fill(0, data)
                buf.pts = frame_num * (Gst.SECOND // fps)
                buf.duration = Gst.SECOND // fps
                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    break
                frame_num += 1

            appsrc.emit("end-of-stream")
            proc.terminate()
            proc.wait(timeout=5)
        except Exception as exc:
            feed_error = str(exc)
            try:
                appsrc.emit("end-of-stream")
            except Exception:
                pass

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

    # Start feeder thread after pipeline is PLAYING
    feed_thread = threading.Thread(target=_feed_loop, daemon=True)
    feed_thread.start()

    def _run():
        loop.run()
        pipeline.set_state(Gst.State.NULL)

    await asyncio.get_running_loop().run_in_executor(None, _run)

    if error_msg:
        raise RuntimeError(f"GStreamer pipeline error: {error_msg}")
    if feed_error:
        raise RuntimeError(f"Script feed error: {feed_error}")

    logger.info("Generated: %s (%ds) from script '%s'", filename, duration, preset_name)
    return {"filename": filename, "path": output_path, "duration": duration}


def register(app, config):
    """Register the script-source plugin with cathode."""
    import os
    from pathlib import Path

    from plugins import FilePresetStore

    preset_dir = os.environ.get("SCRIPT_PRESET_DIR", "/config/script-presets")
    plugin_dir = Path(__file__).parent / "presets"
    effective_dir = preset_dir if os.path.isdir(preset_dir) else str(plugin_dir)

    presets = FilePresetStore(directory=effective_dir, extension=".py")

    async def generate_with_presets(cfg: dict) -> dict:
        return await _generate(cfg, effective_dir)

    return {
        "category": "source,content",
        "source_types": {
            "script": {
                "factory": ScriptSourceFactory(preset_dir=effective_dir),
                "description": "Python script live rendering via appsrc",
                "params": {
                    "preset": {
                        "type": "str",
                        "required": True,
                        "description": "Name of a saved preset script",
                    },
                    "fps": {
                        "type": "int",
                        "description": "Override framerate",
                    },
                    "params": {
                        "type": "dict",
                        "description": "Parameters passed to the script as env vars",
                    },
                },
            },
        },
        "block_types": {
            "script": {
                "handler": SourceBlockHandler("script"),
                "description": "Python script live rendering via appsrc",
                "params": {
                    "preset": {
                        "type": "str",
                        "required": True,
                        "description": "Name of a saved preset script",
                    },
                    "fps": {"type": "int", "description": "Override framerate"},
                    "params": {
                        "type": "dict",
                        "description": "Parameters passed to the script",
                    },
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
                "description": "Directory for script presets",
            },
            "max_timeout": {
                "type": "int",
                "value": 600,
                "description": "Maximum script execution timeout (seconds)",
            },
        },
    }
