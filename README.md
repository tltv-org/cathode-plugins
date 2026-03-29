# Cathode Plugins

Optional plugins for the [cathode](https://github.com/tltv-org/cathode) TLTV server. Cathode works without any plugins — these extend it with source types, overlays, and content tools.

## Plugins

| Plugin | Category | What it adds |
|---|---|---|
| **html-source** | source, content | HTML/CSS/JS rendering via WPE WebKit (wpesrc) |
| **script-source** | source, content | Python script live rendering via appsrc |
| **gstreamer-source** | source, content | Native GStreamer pattern/generator sources |
| **overlay** | graphics | Post-mix overlays: text, image bugs, SVG |

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

**html-source** — 7 HTML presets:
- `bumps` — Adult Swim-style text card interstitials
- `seance` — dark ethereal text with film grain
- `weather` — retro weather channel display
- `channel_zero` — Mandelbrot zoom + uptime counter
- `channel-one-intro` — channel intro card
- `game-of-life` — Conway's Game of Life
- `mandelbrot-zoom` — animated Mandelbrot fractal

**script-source** — 8 Python presets:
- `geometric_shapes` — pulsing concentric shapes with color cycling
- `color_bars_glitch` — glitched SMPTE color bars
- `ascii_text_wave` — ASCII text wave animation
- `emergency_broadcast` — EBS alert screen with colored bars
- `pixel_sort_corruption` — pixel sorting glitch art
- `retro_computer_boot` — retro computer boot sequence
- `scan_line_tv_static` — TV static with scan lines
- `youtube_poop_chaos` — chaotic visual effects

**gstreamer-source** — 3 JSON presets:
- `smpte-with-tone` — SMPTE color bars + 1kHz sine tone
- `bars-silent` — SMPTE bars with "STANDBY" text, silence
- `snow` — static/snow + white noise

**overlay** — 2 JSON presets:
- `bugs/channel-id` — channel ID bug config
- `tickers/default` — default ticker config

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

## License

MIT -- see [LICENSE](LICENSE).
