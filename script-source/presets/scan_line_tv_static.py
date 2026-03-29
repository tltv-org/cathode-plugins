#!/usr/bin/env python3
"""Old TV static with scan lines, interference, and vertical hold slips."""

import os
import random
import sys

from PIL import Image, ImageChops

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30

# ── Pre-render scan-line overlay (reused every frame) ────────────────────

scanlines = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
for y in range(0, HEIGHT, 3):
    scanlines.paste((0, 0, 0, 100), (0, y, WIDTH, y + 1))

rng = random.Random(42)

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    # Random noise — fast C-level operation.
    noise_data = os.urandom(WIDTH * HEIGHT * 3)
    img = Image.frombytes("RGB", (WIDTH, HEIGHT), noise_data).convert("RGBA")

    # Scan-line darkening.
    img = Image.alpha_composite(img, scanlines)

    # Occasional bright horizontal interference band.
    if rng.random() < 0.1:
        y = rng.randint(0, HEIGHT - 1)
        band_h = rng.randint(1, 4)
        for dy in range(band_h):
            if y + dy < HEIGHT:
                img.paste((255, 255, 255, 255), (0, y + dy, WIDTH, y + dy + 1))

    # Occasional vertical hold slip (whole frame shifts down).
    if rng.random() < 0.03:
        slip = rng.randint(10, HEIGHT // 4)
        img = ImageChops.offset(img, 0, slip)

    # Rare horizontal tear — shift a block of rows sideways.
    if rng.random() < 0.05:
        tear_y = rng.randint(0, HEIGHT - 40)
        tear_h = rng.randint(10, 40)
        tear_shift = rng.randint(-WIDTH // 4, WIDTH // 4)
        strip = img.crop((0, tear_y, WIDTH, tear_y + tear_h))
        strip = ImageChops.offset(strip, tear_shift, 0)
        img.paste(strip, (0, tear_y))

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
