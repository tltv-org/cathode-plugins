#!/usr/bin/env python3
"""ASCII art text flowing in a sine wave pattern — green on black."""

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=<>{}[]"

# ── Font setup ───────────────────────────────────────────────────────────

FONT_SIZE = max(12, HEIGHT // 40)
try:
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", FONT_SIZE
    )
except (IOError, OSError):
    font = ImageFont.load_default()

# Approximate monospace character cell size.
char_w = max(1, FONT_SIZE * 3 // 5)
char_h = FONT_SIZE + 2
cols = WIDTH // char_w + 2
rows = HEIGHT // char_h + 2

wave_amp = char_h * 1.8
scroll_speed = 80  # pixels per second

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    t = frame_num / FPS
    img = Image.new("RGBA", (WIDTH, HEIGHT), (5, 0, 15, 255))
    draw = ImageDraw.Draw(img)

    x_offset = int(t * scroll_speed) % char_w

    for row in range(rows):
        for col in range(cols):
            x = col * char_w - x_offset
            wave = math.sin(x * 0.012 + t * 2.5) * wave_amp
            y = int(row * char_h + wave)

            if y < -char_h or y > HEIGHT:
                continue

            ci = (col + row * 7 + int(t * 5)) % len(CHARS)
            ch = CHARS[ci]

            green = 160 + int(60 * math.sin(row * 0.5 + t))
            blue = 40 + int(100 * math.sin(col * 0.2 + t * 0.7))
            color = (0, max(0, min(255, green)), max(0, min(255, blue)), 255)

            draw.text((x, y), ch, fill=color, font=font)

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
