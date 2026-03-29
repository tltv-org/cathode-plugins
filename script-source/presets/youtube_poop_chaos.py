#!/usr/bin/env python3
"""Rapid cuts, glitch effects, text overlays — YTP aesthetic chaos."""

import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30

chaos_level = float(os.environ.get("PARAM_chaos_level", "0.8"))
text_density = float(os.environ.get("PARAM_text_density", "0.5"))

# ── Text fragments and palette ───────────────────────────────────────────

TEXTS = [
    "WHAT",
    "NO",
    "YES",
    "MAYBE",
    "PERHAPS",
    "DEFINITELY NOT",
    "ERROR",
    "GLITCH",
    "CORRUPTED",
    "BROKEN",
    "FIXED",
    "THIS IS FINE",
    "EVERYTHING IS FINE",
    "NOTHING IS FINE",
    "CHANNEL ONE",
    "EXPERIMENTAL TELEVISION",
    "MISTAKE",
    "OOPS",
    "SORRY",
    "NOT SORRY",
    "WE INTERRUPT",
    "TECHNICAL DIFFICULTIES",
    "STAND BY",
    "STANDBY",
    "???",
    "!!!",
    "...",
    "WHAT WAS THAT",
]

PALETTE = [
    (255, 0, 102, 255),
    (0, 255, 170, 255),
    (255, 255, 0, 255),
    (0, 255, 255, 255),
    (255, 0, 255, 255),
    (255, 255, 255, 255),
    (0, 0, 0, 255),
    (128, 128, 128, 255),
]

# ── Pre-load fonts at several sizes ──────────────────────────────────────

_font_cache = {}


def pick_font(size):
    snapped = max(20, (size // 20) * 20)
    if snapped not in _font_cache:
        try:
            _font_cache[snapped] = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", snapped
            )
        except (IOError, OSError):
            _font_cache[snapped] = ImageFont.load_default()
    return _font_cache[snapped]


rng = random.Random(42)

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    t = frame_num / FPS

    # Background: mostly dark, occasional full-color flash.
    if rng.random() < chaos_level * 0.1:
        bg = rng.choice(
            [
                (255, 0, 102, 255),
                (0, 255, 170, 255),
                (0, 0, 0, 255),
                (255, 255, 255, 255),
            ]
        )
    else:
        bg = (26, 26, 46, 255)

    img = Image.new("RGBA", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)

    # Random text overlays.
    if rng.random() < text_density:
        n = rng.randint(1, max(1, int(5 * chaos_level)))
        for _ in range(n):
            text = rng.choice(TEXTS)
            color = rng.choice(PALETTE)
            size = rng.randint(40, 200)
            x = rng.randint(-100, WIDTH - 100)
            y = rng.randint(-50, HEIGHT - 50)
            draw.text((x, y), text, fill=color, font=pick_font(size))

    # Glitch rectangles.
    if rng.random() < chaos_level * 0.3:
        n = rng.randint(1, 10)
        for _ in range(n):
            x1 = rng.randint(0, WIDTH - 50)
            y1 = rng.randint(0, HEIGHT - 50)
            x2 = x1 + rng.randint(20, 300)
            y2 = y1 + rng.randint(10, 200)
            draw.rectangle([x1, y1, x2, y2], fill=rng.choice(PALETTE))

    # Color inversion of a random section.
    if rng.random() < chaos_level * 0.15:
        ix = rng.randint(0, max(1, WIDTH - 100))
        iy = rng.randint(0, max(1, HEIGHT - 100))
        iw = rng.randint(50, 400)
        ih = rng.randint(50, 300)
        box = (ix, iy, min(ix + iw, WIDTH), min(iy + ih, HEIGHT))
        section = img.crop(box).convert("RGB")
        section = ImageOps.invert(section).convert("RGBA")
        img.paste(section, (ix, iy))

    # Random horizontal line noise.
    if rng.random() < chaos_level * 0.2:
        for _ in range(rng.randint(1, 5)):
            ly = rng.randint(0, HEIGHT - 1)
            row = Image.frombytes("RGB", (WIDTH, 1), os.urandom(WIDTH * 3)).convert(
                "RGBA"
            )
            img.paste(row, (0, ly))

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
