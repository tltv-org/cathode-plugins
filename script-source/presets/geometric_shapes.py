#!/usr/bin/env python3
"""Expanding and contracting geometric shapes with color cycling."""

import math
import os
import sys

from PIL import Image, ImageDraw

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 30

speed = float(os.environ.get("PARAM_speed", "1.0"))
num_shapes = int(os.environ.get("PARAM_num_shapes", "8"))


def hsv_to_rgb(h, s, v):
    """Convert HSV (h 0-360, s/v 0-1) to RGBA tuple."""
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


cx, cy = WIDTH // 2, HEIGHT // 2
max_radius = int(min(WIDTH, HEIGHT) * 0.45)

frame_num = 0

while True:
    t = frame_num / FPS
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    for i in range(num_shapes):
        phase = t * speed * 2.0 + i * (2 * math.pi / num_shapes)
        radius = int(abs(math.sin(phase)) * max_radius) + 10

        hue = (t * speed * 40 + i * (360 / num_shapes)) % 360
        color = hsv_to_rgb(hue, 0.9, 1.0)

        line_w = max(2, 4 - i // 3)

        if i % 2 == 0:
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=color,
                width=line_w,
            )
        else:
            draw.rectangle(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=color,
                width=line_w,
            )

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
