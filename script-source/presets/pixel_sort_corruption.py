#!/usr/bin/env python3
"""Pixel sorting glitch art — datamosh aesthetic with animated threshold."""

import math
import os
import random
import sys

from PIL import Image, ImageDraw

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30


def hsv_to_rgb(h, s, v):
    """HSV to RGBA: h 0-360, s/v 0-1."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255), 255)


# ── Build base gradient (vertical rainbow + horizontal brightness) ───────

# Single-column rainbow stretched to full width.
column = Image.new("RGBA", (1, HEIGHT))
for y in range(HEIGHT):
    column.putpixel((0, y), hsv_to_rgb(y * 360 / HEIGHT, 0.9, 1.0))
rainbow = column.resize((WIDTH, HEIGHT), Image.NEAREST)

# Horizontal brightness mask (sine wave: bright center, dark edges).
grad = Image.new("L", (WIDTH, HEIGHT), 0)
grad_draw = ImageDraw.Draw(grad)
for x in range(WIDTH):
    v = int(40 + 215 * math.sin(x * math.pi / WIDTH))
    grad_draw.line([(x, 0), (x, HEIGHT - 1)], fill=v)

# Composite rainbow over black using brightness mask.
black = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
base = Image.composite(rainbow, black, grad)

# ── Pre-compute fully sorted version ─────────────────────────────────────

base_pixels = list(base.tobytes())  # flat RGBA bytes
# Regroup into per-pixel RGBA tuples for sorting
base_pixels = [
    (base_pixels[i], base_pixels[i + 1], base_pixels[i + 2], base_pixels[i + 3])
    for i in range(0, len(base_pixels), 4)
]
sorted_pixels = list(base_pixels)
for y in range(HEIGHT):
    start = y * WIDTH
    row = sorted_pixels[start : start + WIDTH]
    row.sort(key=sum)
    sorted_pixels[start : start + WIDTH] = row
sorted_base = Image.new("RGBA", (WIDTH, HEIGHT))
sorted_base.putdata(sorted_pixels)

# ── Assign random activation times to each row ──────────────────────────

rng = random.Random(42)
row_sort_time = [rng.random() for _ in range(HEIGHT)]
sorted_order = sorted(range(HEIGHT), key=lambda y: row_sort_time[y])

# ── Render frames ────────────────────────────────────────────────────────

mask = Image.new("L", (WIDTH, HEIGHT), 0)
next_idx = 0

frame_num = 0

while True:
    t = frame_num / FPS
    progress = min(t / DURATION, 1.0)

    # Activate rows whose random threshold < current progress.
    while next_idx < HEIGHT and row_sort_time[sorted_order[next_idx]] < progress:
        y = sorted_order[next_idx]
        mask.paste(255, (0, y, WIDTH, y + 1))
        next_idx += 1

    img = Image.composite(sorted_base, base, mask)

    # Occasional glitch noise lines (frequency increases with progress).
    if rng.random() < 0.12 * progress:
        gy = rng.randint(0, HEIGHT - 1)
        noise = Image.frombytes("RGB", (WIDTH, 1), os.urandom(WIDTH * 3))
        img.paste(noise.convert("RGBA"), (0, gy))

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
