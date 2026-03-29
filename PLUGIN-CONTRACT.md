# Cathode Plugin Contract

Every plugin must expose a `register(app, config)` function.

## Installation

**Drop-in:** Copy the plugin directory into cathode's `app/plugins/` directory.

**pip:** Install as a Python package with a `cathode.plugins` entry point.

```bash
pip install cathode-plugin-html-source
```

**Enable/disable:** Plugins with a `.disabled` file in their directory
are discovered but not loaded. Use the API:

```bash
POST /api/plugins/{name}/disable    # creates .disabled, restart required
POST /api/plugins/{name}/enable     # removes .disabled, restart required
```

## Route Namespace

All plugin routes are enforced under `/api/plugins/{name}/*`.  The
`app` passed to `register()` is a `PluginApp` wrapper that intercepts
`include_router()` and rewrites all route paths into the plugin's
namespace.  Plugins call `app.include_router(router)` normally — the
wrapper handles the rest.  Plugins cannot register routes outside
their namespace.

Example: if the overlay plugin creates `APIRouter(prefix="/api/overlay")`
with a route `@router.get("/text")`, the final path will be
`/api/plugins/overlay/text`.

## Interface

```python
def register(app, config) -> dict | None:
    """Called by cathode on startup.

    Args:
        app: PluginApp wrapper (proxies to FastAPI, enforces route namespace).
        config: The cathode config module.

    Returns:
        Optional dict with:

        # Identity
        "category": "source",          # source|content|schedule|graphics|output|integration

        # Core lifecycle (unchanged from v1)
        "shutdown": async_cleanup_fn,   # called on app shutdown
        "services": {"name": instance}, # registered in service registry
        "tasks": [coroutine_fn],        # background tasks started after load
        "settings": {                   # runtime-configurable settings
            "key": {
                "type": "str",          # str|int|float|bool
                "value": "default",     # current value
                "description": "...",
            },
        },
        "on_settings_changed": async_callback(settings_dict),

        # Engine extensions (require engine restart)
        "source_types": {               # new input types for layers
            "html": {
                "factory": HTMLSourceFactory(),
                "description": "HTML rendering via WPE WebKit",
                "params": {
                    "location": {"type": "str", "description": "URL to render"},
                },
            },
        },
        "output_types": {               # new output destinations
            "srt": {
                "factory": SRTOutputFactory(),
                "description": "SRT output",
                "params": {"uri": {"type": "str"}},
            },
        },
        "block_types": {                # new schedule block types
            "auto-bumper": {
                "handler": BumperHandler(),
                "description": "Auto-generated channel ident",
            },
        },
        "overlay_elements": [           # post-mix overlay elements
            # (GStreamer factory, element name, default properties)
            ("textoverlay", "text-overlay", {"silent": True}),
            ("gdkpixbufoverlay", "bug-overlay", {"alpha": 0.0}),
        ],
        "layers": [                     # additional compositor layers
            {"name": "graphics", "role": "overlay"},
        ],
        "playlist_tools": {             # playlist transformation tools
            "sort": {
                "handler": SortTool(),
                "description": "Sort playlist entries",
                "params": {"by": {"type": "str"}},
            },
        },

        # Documentation
        "system_deps": ["gstreamer1.0-wpe"],  # for validation/warnings
    }
```

All fields are optional. A plugin only declares what it provides.

## Categories

| Category | What it does | Example plugins |
|---|---|---|
| `source` | New input types for playout layers | html-source, script-source, gstreamer-source |
| `content` | Produce/manage media files | ffmpeg-gen, script-source (file mode) |
| `schedule` | Auto-populate program blocks | auto-schedule |
| `graphics` | Inline overlay on the composited mix | overlay |
| `output` | New output destinations | srt, ndi |
| `integration` | External service bridges | webhook, metrics |

A plugin may declare multiple categories as a comma-separated string
(e.g. `"source,content"`).

## Source Type Factory

Source plugins register a factory that builds GStreamer pipelines on
an InputLayer:

```python
class HTMLSourceFactory:
    def build(self, layer, config: dict) -> None:
        """Build GStreamer elements on the given InputLayer.

        Args:
            layer: InputLayer instance. Key attributes:
                layer._pipeline   — GstPipeline to add elements to
                layer._v_sink     — intervideosink to link video to
                layer._a_sink     — interaudiosink to link audio to
                layer._config     — MixerConfig (width, height, fps, audio)
                layer._link_to_output(v_pad, a_pad) — link helper
                layer._source_elements — list to store elements for teardown
                layer.index       — channel index for element naming
            config: Source config dict from the API request.
        """
        # Create elements, add to pipeline, link to inter sinks
```

The InputLayer handles lifecycle: teardown, start, error → failover.
Build failures fall back to black test pattern.

## Dependencies

Each plugin can have a `requirements.txt` for Python dependencies.
Cathode pip-installs them at startup with constraints from
`plugin_constraints.txt` to prevent breaking core packages.

System dependencies (apt packages) are declared in `system_deps`
and validated at load time. Missing system deps log a warning.

## Testing

Plugin tests live alongside the plugin:

```
my-plugin/
├── __init__.py
├── presets/
└── tests/
    ├── conftest.py     # plugin-specific fixtures
    └── test_my_plugin.py
```

Run via: `pytest /app/plugins/*/tests/ -v`
```
