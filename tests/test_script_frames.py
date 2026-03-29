"""Test that script presets produce valid RGBA frame output.

Runs each script as a subprocess with a small resolution and short
duration, verifying it outputs correctly-sized raw RGBA data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

PRESET_DIR = REPO_ROOT / "script-source" / "presets"

# Use small resolution for fast tests
TEST_WIDTH = 320
TEST_HEIGHT = 240
TEST_FPS = 10
TEST_DURATION = 1  # 1 second = 10 frames
FRAME_SIZE = TEST_WIDTH * TEST_HEIGHT * 4  # RGBA


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


@pytest.mark.parametrize("name", SCRIPT_PRESETS)
def test_script_produces_frames(name):
    """Run the script and verify it produces at least one valid RGBA frame."""
    script_path = PRESET_DIR / f"{name}.py"
    assert script_path.exists(), f"Script not found: {script_path}"

    env = {
        "WIDTH": str(TEST_WIDTH),
        "HEIGHT": str(TEST_HEIGHT),
        "FPS": str(TEST_FPS),
        "DURATION": str(TEST_DURATION),
        "HOME": "/tmp",
        "PATH": "/usr/bin:/bin",
    }

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        timeout=30,
        env=env,
    )

    # Check it didn't crash
    assert result.returncode == 0, (
        f"Script {name} exited with code {result.returncode}.\n"
        f"stderr: {result.stderr.decode(errors='replace')[:500]}"
    )

    # Check output size is a multiple of frame_size
    output_len = len(result.stdout)
    assert output_len > 0, f"Script {name} produced no output"
    assert output_len >= FRAME_SIZE, (
        f"Script {name} produced {output_len} bytes, "
        f"expected at least {FRAME_SIZE} (one frame at {TEST_WIDTH}x{TEST_HEIGHT} RGBA)"
    )
    assert output_len % FRAME_SIZE == 0, (
        f"Script {name} output ({output_len} bytes) is not a multiple of "
        f"frame size ({FRAME_SIZE}). Partial frame detected."
    )

    num_frames = output_len // FRAME_SIZE
    expected_frames = TEST_FPS * TEST_DURATION
    # Allow some tolerance — scripts may produce slightly fewer frames
    assert num_frames >= expected_frames - 2, (
        f"Script {name} produced {num_frames} frames, expected ~{expected_frames}"
    )


@pytest.mark.parametrize("name", SCRIPT_PRESETS)
def test_script_no_stderr_errors(name):
    """Scripts should not produce error output during normal operation."""
    script_path = PRESET_DIR / f"{name}.py"

    env = {
        "WIDTH": str(TEST_WIDTH),
        "HEIGHT": str(TEST_HEIGHT),
        "FPS": str(TEST_FPS),
        "DURATION": str(TEST_DURATION),
        "HOME": "/tmp",
        "PATH": "/usr/bin:/bin",
    }

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        timeout=30,
        env=env,
    )

    stderr = result.stderr.decode(errors="replace").strip()
    # Filter out Python warnings (multi-line: "file:line: WarningType: msg\n  code")
    lines = stderr.splitlines()
    filtered = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if "Warning:" in line or "DeprecationWarning" in line:
            skip_next = True  # skip the code context line that follows
            continue
        filtered.append(line)
    error_lines = "\n".join(filtered).strip()
    assert not error_lines, (
        f"Script {name} produced unexpected stderr:\n{error_lines[:500]}"
    )
