#!/usr/bin/env python3
"""
BearBox — Display Engine
Handles all drawing and framebuffer output.
Every screen draws to a PIL Image then calls push().

Usage:
    from display import new_frame, push, W, H
    img, draw = new_frame()
    draw.rectangle([0, 0, W, H], fill=C["bg"])
    draw.text((10, 10), "Hello!", font=font(20), fill=C["white"])
    push(img)
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
W       = 480
H       = 320
FB_DEV  = "/dev/fb1"

# ─────────────────────────────────────────────────────────────
# PALETTE
# ─────────────────────────────────────────────────────────────
C = {
    "bg":       (0,    5,   15),
    "blue":     (0,   180, 255),
    "midblue":  (0,   120, 200),
    "dimblue":  (0,    40,  80),
    "white":    (240, 248, 255),
    "dimwhite": (100, 120, 145),
    "green":    (0,   255, 80),
    "dimgreen": (0,   80,  35),
    "dim":      (15,  30,  50),
    "panel":    (5,   15,  30),
    "amber":    (255, 176,  0),
    "red":      (255,  50,  50),
    "black":    (0,   0,   0),
}

# ─────────────────────────────────────────────────────────────
# FONT LOADER
# ─────────────────────────────────────────────────────────────

_font_cache = {}

def font(size, bold=False, path=None):
    """
    Load a font by size. Caches for performance.
    path: optional .ttf file path
    bold: tries to find bold variant of system font
    """
    key = (size, bold, path)
    if key in _font_cache:
        return _font_cache[key]

    f = None

    # try custom path first
    if path and os.path.exists(path):
        try:
            f = ImageFont.truetype(path, size)
        except:
            pass

    # try fonts folder relative to this file
    if f is None:
        fonts_dir = os.path.join(os.path.dirname(__file__), "../fonts")
        for fname in os.listdir(fonts_dir) if os.path.exists(fonts_dir) else []:
            if fname.endswith(".ttf"):
                try:
                    f = ImageFont.truetype(os.path.join(fonts_dir, fname), size)
                    break
                except:
                    pass

    # try system fonts
    if f is None:
        system_fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold else
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
        for fp in system_fonts:
            if os.path.exists(fp):
                try:
                    f = ImageFont.truetype(fp, size)
                    break
                except:
                    pass

    # fallback to PIL default
    if f is None:
        f = ImageFont.load_default()

    _font_cache[key] = f
    return f

# ─────────────────────────────────────────────────────────────
# FRAME + PUSH
# ─────────────────────────────────────────────────────────────

def new_frame(bg=None):
    """Create a new blank frame. Returns (Image, ImageDraw)."""
    img  = Image.new("RGB", (W, H), bg or C["bg"])
    draw = ImageDraw.Draw(img)
    return img, draw

def push(img):
    """Write a PIL Image directly to the framebuffer as RGB565."""
    rgb    = img.convert("RGB")
    arr    = np.array(rgb, dtype=np.uint16)
    r      = (arr[:, :, 0] >> 3).astype(np.uint16)
    g      = (arr[:, :, 1] >> 2).astype(np.uint16)
    b      = (arr[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    with open(FB_DEV, "wb") as f:
        f.write(rgb565.tobytes())

# ─────────────────────────────────────────────────────────────
# DRAW HELPERS
# ─────────────────────────────────────────────────────────────

def draw_text_centered(draw, text, fnt, color, y):
    """Draw text horizontally centered."""
    bbox = fnt.getbbox(text)
    tw   = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y), text, font=fnt, fill=color)

def draw_bar(draw, x, y, w, h, pct, color, bg=None):
    """Draw a horizontal progress bar."""
    bg = bg or C["dim"]
    draw.rectangle([x, y, x+w, y+h], fill=bg, outline=C["dimblue"])
    filled = int(w * min(pct / 100.0, 1.0))
    if filled > 0:
        draw.rectangle([x, y, x+filled, y+h], fill=color)

def draw_scanlines(draw, alpha=12):
    """Draw subtle scanline overlay."""
    for y in range(0, H, 4):
        draw.line([(0, y), (W, y)], fill=(0, alpha, alpha*2))

def draw_corner_brackets(draw, color, size=16, thickness=2):
    """Draw corner bracket decorations."""
    c = color
    # top left
    draw.line([(6, 6), (6+size, 6)],     fill=c, width=thickness)
    draw.line([(6, 6), (6, 6+size)],     fill=c, width=thickness)
    # top right
    draw.line([(W-6, 6), (W-6-size, 6)], fill=c, width=thickness)
    draw.line([(W-6, 6), (W-6, 6+size)], fill=c, width=thickness)
    # bottom left
    draw.line([(6, H-6), (6+size, H-6)], fill=c, width=thickness)
    draw.line([(6, H-6), (6, H-6-size)], fill=c, width=thickness)
    # bottom right
    draw.line([(W-6, H-6), (W-6-size, H-6)], fill=c, width=thickness)
    draw.line([(W-6, H-6), (W-6, H-6-size)], fill=c, width=thickness)

def wrap_text(text, fnt, max_w):
    """Wrap text into lines that fit max_w pixels."""
    words  = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        bbox = fnt.getbbox(test)
        if bbox[2] - bbox[0] <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines