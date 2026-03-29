#!/usr/bin/env python3
"""SMPTE color bars with progressive glitch distortion."""

import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30

glitch_speed = float(os.environ.get("PARAM_glitch_speed", "1.0"))
max_glitch = float(os.environ.get("PARAM_max_glitch", "0.8"))

# ── Base SMPTE color bars (built once) ───────────────────────────────────

BAR_COLORS = [
    (192, 192, 192, 255),
    (192, 192, 0, 255),
    (0, 192, 192, 255),
    (0, 192, 0, 255),
    (192, 0, 192, 255),
    (192, 0, 0, 255),
    (0, 0, 192, 255),
]

base = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
base_draw = ImageDraw.Draw(base)
bar_w = WIDTH // len(BAR_COLORS)
for i, color in enumerate(BAR_COLORS):
    x0 = i * bar_w
    x1 = (i + 1) * bar_w if i < len(BAR_COLORS) - 1 else WIDTH
    base_draw.rectangle([x0, 0, x1, HEIGHT], fill=color)

rng = random.Random(42)

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    t = frame_num / FPS
    progress = min(t * glitch_speed / max(DURATION, 1), 1.0) * max_glitch

    img = base.copy()

    # Glitch 1: horizontal row shifts (VHS tracking errors)
    if progress > 0.0:
        num_shifts = int(progress * 50)
        for _ in range(num_shifts):
            y = rng.randint(0, HEIGHT - 1)
            max_shift = max(1, int(progress * WIDTH * 0.2))
            shift = rng.randint(-max_shift, max_shift)
            if shift == 0:
                continue
            row = img.crop((0, y, WIDTH, y + 1))
            if shift > 0:
                left = row.crop((WIDTH - shift, 0, WIDTH, 1))
                right = row.crop((0, 0, WIDTH - shift, 1))
                img.paste(left, (0, y))
                img.paste(right, (shift, y))
            else:
                s = -shift
                left = row.crop((s, 0, WIDTH, 1))
                right = row.crop((0, 0, s, 1))
                img.paste(left, (0, y))
                img.paste(right, (WIDTH - s, y))

    # Glitch 2: RGB channel separation (chromatic aberration)
    if progress > 0.1:
        sep = int(progress * 20)
        r, g, b, a = img.split()
        r = ImageChops.offset(r, sep, 0)
        b = ImageChops.offset(b, -sep, 0)
        img = Image.merge("RGBA", (r, g, b, a))

    # Glitch 3: random block corruption
    if progress > 0.3:
        draw = ImageDraw.Draw(img)
        num_blocks = int(progress * 10)
        for _ in range(num_blocks):
            bx = rng.randint(0, max(1, WIDTH - 50))
            by = rng.randint(0, max(1, HEIGHT - 20))
            bw = rng.randint(20, 100)
            bh = rng.randint(5, 30)
            color = (
                rng.randint(0, 255),
                rng.randint(0, 255),
                rng.randint(0, 255),
                255,
            )
            draw.rectangle([bx, by, bx + bw, by + bh], fill=color)

    # Glitch 4: scan-line noise
    if progress > 0.2:
        n_lines = int(progress * 20)
        for _ in range(n_lines):
            y = rng.randint(0, HEIGHT - 1)
            row_data = os.urandom(WIDTH * 3)
            row_img = Image.frombytes("RGB", (WIDTH, 1), row_data).convert("RGBA")
            img.paste(row_img, (0, y))

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
