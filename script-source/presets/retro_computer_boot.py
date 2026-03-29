#!/usr/bin/env python3
"""Retro computer boot sequence — green phosphor text on black CRT."""

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 45

# ── Boot messages: (appear_time_seconds, text) ──────────────────────────

BOOT_LINES = [
    (0.0, "CHANNEL ONE BROADCAST SYSTEM v1.0"),
    (0.8, "Copyright (c) 2026 TLTV Project"),
    (1.8, ""),
    (2.0, "POST diagnostics:"),
    (2.5, "  CPU ..................... OK"),
    (3.5, "  Memory ................. 640K OK"),
    (4.5, "  Video subsystem ........ OK"),
    (5.5, "  Audio subsystem ........ OK"),
    (6.5, ""),
    (7.0, "Loading video subsystem .......... OK"),
    (8.5, "Loading generator modules ......... OK"),
    (10.0, "Mounting archive filesystem ....... OK"),
    (11.5, "Starting playout engine ........... OK"),
    (13.0, "Calibrating color output .......... OK"),
    (14.5, ""),
    (15.0, "All systems nominal."),
    (16.0, ""),
    (16.5, "SYSTEM READY"),
    (17.5, ""),
    (18.0, "> BEGIN TRANSMISSION"),
]

# ── Font setup ───────────────────────────────────────────────────────────

FONT_SIZE = max(14, HEIGHT // 35)
try:
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", FONT_SIZE
    )
except (IOError, OSError):
    font = ImageFont.load_default()

LINE_HEIGHT = FONT_SIZE + 4
MARGIN_X = max(20, WIDTH // 30)
MARGIN_Y = max(20, HEIGHT // 20)
CHAR_RATE = 50  # characters per second (typewriter speed)

# ── Pre-render scan-line overlay (reused every frame) ────────────────────

scanlines = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
for y in range(0, HEIGHT, 3):
    scanlines.paste((0, 0, 0, 50), (0, y, WIDTH, y + 1))

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    t = frame_num / FPS
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    y = MARGIN_Y
    still_typing = False

    for appear_time, full_text in BOOT_LINES:
        if t < appear_time:
            break

        # Blank lines just advance the cursor.
        if full_text == "":
            y += LINE_HEIGHT
            continue

        elapsed = t - appear_time
        chars = min(len(full_text), int(elapsed * CHAR_RATE))
        visible = full_text[:chars]

        # Show blinking cursor on the line currently being typed.
        still_typing = chars < len(full_text)
        if still_typing and int(t * 4) % 2 == 0:
            visible += "_"

        # Green phosphor color with slight scanline variation.
        green = 190 + int(40 * math.sin(y * 0.1 + t))
        color = (0, min(255, green), 0, 255)

        draw.text((MARGIN_X, y), visible, fill=color, font=font)
        y += LINE_HEIGHT

    # Blinking block cursor after all lines are done.
    if not still_typing:
        last_time = BOOT_LINES[-1][0]
        last_len = len(BOOT_LINES[-1][1])
        if t > last_time + last_len / CHAR_RATE + 0.5:
            if int(t * 2) % 2 == 0:
                draw.text((MARGIN_X, y), "_", fill=(0, 220, 0, 255), font=font)

    # Apply scan-line overlay.
    img = Image.alpha_composite(img, scanlines)

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
