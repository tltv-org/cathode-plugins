# Cathode Plugins

Optional plugins for the [cathode](https://git.plutoniumtech.com/tltv/cathode) TLTV server. Cathode works without any plugins — these extend it with source types, overlays, and content tools.

## Plugins

| Plugin | Category | What it adds |
|---|---|---|
| **html-source** | source, content | HTML/CSS/JS rendering via WPE WebKit (wpesrc). 7 HTML presets. |
| **script-source** | source, content | Python script live rendering (appsrc) + file generation. 8 presets. |
| **gstreamer-source** | source, content | Native GStreamer pattern/generator sources. 3 JSON presets. |
| **overlay** | graphics | Post-mix overlays: text, image bugs (PNG/JPEG), SVG. |

All source plugins register: source types, schedule block types, presets, and generate handlers.
All plugins expose settings via `GET/PATCH /api/plugins/{name}/settings`.

Enable/disable at runtime: `POST /api/plugins/{name}/enable` or `/disable`.

## Install

Plugins are volume-mounted into the cathode container:

```yaml
# docker-compose.yml
volumes:
  - ./cathode-plugins:/app/plugins
```

Python dependencies are auto-installed at startup from each plugin's `requirements.txt`.

System dependencies (like WPE WebKit for html-source) require `cathode:latest` (full image). Pure Python plugins work on `cathode:slim`.

## Source Plugins

Source plugins register new input types for the playout engine's layers.

```bash
# HTML rendering (wpesrc — in-process, no sidecar container)
POST /api/playout/layers/input_a/source
{ "type": "html", "location": "file:///app/plugins/html-source/presets/seance.html" }

# Python script (appsrc — subprocess feeds raw frames)
POST /api/playout/layers/input_a/source
{ "type": "script", "preset": "geometric_shapes" }

# GStreamer generator (native elements — pure GStreamer)
POST /api/playout/layers/input_a/source
{ "type": "generator", "preset": "smpte-with-tone" }
```

## Overlay Plugin

Post-mix graphics overlay. Registers elements between the mixer's
compositor and output. No new layer — inline processing.

```bash
# Text overlay
POST /api/plugins/overlay/text?text=BREAKING+NEWS&fontsize=48&position=bottom-center

# Channel bug (PNG logo in corner)
POST /api/plugins/overlay/bug?path=/media/logo.png&x=20&y=20&alpha=0.8

# SVG overlay
POST /api/plugins/overlay/svg?path=/media/lower-third.svg

# Clear all
DELETE /api/plugins/overlay/text
DELETE /api/plugins/overlay/bug
```

All plugin routes are enforced under `/api/plugins/{name}/*` by cathode's
PluginApp wrapper. Plugins cannot register routes outside their namespace.

## Presets

Each plugin includes ready-to-use presets, discoverable via the cathode API:

```bash
GET /api/plugins/{name}/presets              # List all presets
GET /api/plugins/{name}/presets/{preset}     # Get full content
PUT /api/plugins/{name}/presets/{preset}     # Create/update
DELETE /api/plugins/{name}/presets/{preset}  # Delete
```

**html-source** (7 HTML files):
bumps, seance, weather, channel_zero, channel-one-intro, game-of-life, mandelbrot-zoom

**script-source** (8 Python scripts):
geometric_shapes, color_bars_glitch, ascii_text_wave, emergency_broadcast, pixel_sort_corruption, retro_computer_boot, scan_line_tv_static, youtube_poop_chaos

**gstreamer-source** (3 JSON configs):
smpte-with-tone, bars-silent, snow

**overlay** (2 JSON configs):
bugs/channel-id, tickers/default

## Media Generation

Source plugins with generate support can render presets to MP4 files
in the media library:

```bash
POST /api/plugins/gstreamer-source/generate
{ "preset": "smpte-with-tone", "duration": 60, "filename": "bars.mp4" }

POST /api/plugins/script-source/generate
{ "preset": "geometric_shapes", "duration": 30 }

POST /api/plugins/html-source/generate
{ "preset": "seance", "duration": 30 }
```

Generation uses standalone GStreamer pipelines (source → x264enc → mp4mux → filesink).
The generated file appears in the media library automatically.

## Testing

Tests run standalone — no GStreamer, no cathode, no Docker required.
Mocks are provided for cathode's `FilePresetStore`, `main` module, and
`routes.playout` so all 4 plugins can be imported and tested in isolation.

```bash
python3 -m venv .venv
.venv/bin/pip install pytest pytest-anyio fastapi httpx pillow
.venv/bin/python -m pytest tests/ -v
```

198 tests covering: contract compliance, preset validation, script frame
output, HTML template substitution, overlay route handlers, and syntax
checks for all Python/JSON/HTML files.

## Links

- [timelooptv.org](https://timelooptv.org) — Project homepage
- [Spec](https://spec.timelooptv.org) — Protocol specification
- [Demo](https://demo.timelooptv.org) — Live demo
- [GitHub](https://github.com/tltv-org) — All repositories
- [cathode](https://github.com/tltv-org/cathode) — TLTV reference server

## License

[MIT](LICENSE)

## Future Plugins

- **ffmpeg-gen** — JSON→ffmpeg→MP4 file generation
- **auto-schedule** — automatic bumper/ident insertion
- **rtmp** — RTMP listener for OBS push ingest
- **srt** — SRT source + output
- **playlist-tools** — sort, pad, deduplicate playlists
