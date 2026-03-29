#!/usr/bin/env python3
"""Emergency Broadcast System alert screen with colored bars and warning text."""

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
FPS = int(os.environ.get("FPS", "30"))
_dur_env = os.environ.get("DURATION")
DURATION = int(_dur_env) if _dur_env else 60

# ── EBS color bar pattern (red-white-blue-white-red) ─────────────────────

EBS_COLORS = [
    (255, 0, 0),
    (255, 0, 0),
    (255, 0, 0),
    (255, 0, 0),
    (255, 255, 255),
    (255, 255, 255),
    (0, 0, 255),
    (0, 0, 255),
    (0, 0, 255),
    (0, 0, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 0, 0),
    (255, 0, 0),
    (255, 0, 0),
    (255, 0, 0),
]

# ── Warning ticker text ──────────────────────────────────────────────────

WARNING = (
    "THIS IS A TEST OF THE EMERGENCY BROADCAST SYSTEM. "
    "THE BROADCASTERS OF YOUR AREA IN VOLUNTARY COOPERATION WITH FEDERAL, "
    "STATE, AND LOCAL AUTHORITIES HAVE DEVELOPED THIS SYSTEM TO KEEP YOU "
    "INFORMED IN THE EVENT OF AN EMERGENCY. IF THIS HAD BEEN AN ACTUAL "
    "EMERGENCY, YOU WOULD HAVE BEEN INSTRUCTED WHERE TO TUNE IN YOUR AREA "
    "FOR NEWS AND OFFICIAL INFORMATION. THIS CONCLUDES THIS TEST. "
)

# ── Font setup ───────────────────────────────────────────────────────────


def _load_font(bold, size):
    name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except (IOError, OSError):
        return ImageFont.load_default()


font_header = _load_font(True, max(24, HEIGHT // 14))
font_body = _load_font(False, max(16, HEIGHT // 30))
font_ticker = _load_font(False, max(14, HEIGHT // 40))

# ── Layout constants ─────────────────────────────────────────────────────

bar_height = HEIGHT // 6
ticker_height = HEIGHT // 10

# Pre-render the color bars strip (static, reused every frame).
bars_strip = Image.new("RGBA", (WIDTH, bar_height), (0, 0, 0, 255))
bars_draw = ImageDraw.Draw(bars_strip)
bw = WIDTH // len(EBS_COLORS)
for i, c in enumerate(EBS_COLORS):
    x0 = i * bw
    x1 = (i + 1) * bw if i < len(EBS_COLORS) - 1 else WIDTH
    bars_draw.rectangle([x0, 0, x1, bar_height], fill=(*c, 255))

# Measure ticker text width once for scroll wrapping.
_tmp = Image.new("RGBA", (1, 1))
_td = ImageDraw.Draw(_tmp)
ticker_bbox = _td.textbbox((0, 0), WARNING, font=font_ticker)
ticker_text_w = ticker_bbox[2] - ticker_bbox[0]
scroll_cycle = ticker_text_w + WIDTH

# ── Render frames ────────────────────────────────────────────────────────

frame_num = 0

while True:
    t = frame_num / FPS

    # Background alternates dark/darker for a subtle flash.
    flash = int(t * 2) % 2
    bg = (20, 0, 0, 255) if flash == 0 else (40, 0, 5, 255)
    img = Image.new("RGBA", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)

    # Color bars at top.
    img.paste(bars_strip, (0, 0))

    # Header: EMERGENCY ALERT SYSTEM
    header = "EMERGENCY ALERT SYSTEM"
    hbox = draw.textbbox((0, 0), header, font=font_header)
    hw = hbox[2] - hbox[0]
    hh = hbox[3] - hbox[1]
    hy = bar_height + HEIGHT // 10
    draw.text(((WIDTH - hw) // 2, hy), header, fill=(255, 0, 60, 255), font=font_header)

    # Divider line.
    line_y = hy + hh + 20
    draw.line(
        [(WIDTH // 8, line_y), (WIDTH * 7 // 8, line_y)],
        fill=(255, 255, 255, 255),
        width=2,
    )

    # Subtitle.
    sub = "THIS IS A TEST"
    sbox = draw.textbbox((0, 0), sub, font=font_body)
    sw = sbox[2] - sbox[0]
    draw.text(
        ((WIDTH - sw) // 2, line_y + 25),
        sub,
        fill=(255, 255, 255, 255),
        font=font_body,
    )

    # Channel ID.
    chan = "CHANNEL ONE — TLTV BROADCAST"
    cbox = draw.textbbox((0, 0), chan, font=font_body)
    cw = cbox[2] - cbox[0]
    draw.text(
        ((WIDTH - cw) // 2, line_y + 65),
        chan,
        fill=(200, 200, 200, 255),
        font=font_body,
    )

    # Pulsing attention indicator.
    pulse = int(128 + 127 * math.sin(t * 6))
    dot_y = line_y + 110
    draw.ellipse(
        [WIDTH // 2 - 8, dot_y, WIDTH // 2 + 8, dot_y + 16],
        fill=(255, pulse, 0, 255),
    )

    # Bottom ticker bar.
    ticker_y = HEIGHT - ticker_height
    draw.rectangle([0, ticker_y, WIDTH, HEIGHT], fill=(0, 0, 100, 255))
    text_x = WIDTH - int(t * 120) % scroll_cycle
    draw.text(
        (text_x, ticker_y + (ticker_height - 14) // 2),
        WARNING,
        fill=(255, 255, 255, 255),
        font=font_ticker,
    )

    sys.stdout.buffer.write(img.tobytes())
    frame_num += 1

    if _dur_env is not None and frame_num >= FPS * DURATION:
        break
