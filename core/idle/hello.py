#!/usr/bin/env python3
"""
BearBox Idle — HELLO LOSER Screensaver
- Giant centered text with glitch/flicker effect
- Hacking terminal noise in background
- Blue and white color scheme
"""

import time
import os
import sys
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_scanlines, font, C, W, H

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

LINE1      = "NO MODULES"         # first line text
LINE2      = "DETECTED"         # second line text
CREDIT     = "-FD"           # credit text

MAIN_SIZE   = 90             # main text font size
CREDIT_SIZE = 18             # credit font size
BG_SIZE     = 10             # background terminal text size

# ── Position (0.5 = center, 0.0 = left/top, 1.0 = right/bottom)
TEXT_X      = 0.5            # horizontal position (0.0 - 1.0)
TEXT_Y      = 0.4            # vertical position (0.0 - 1.0)
CREDIT_X    = 0.97           # credit horizontal position
CREDIT_Y    = 0.92           # credit vertical position
LINE_GAP    = 8              # gap between LINE1 and LINE2

# ── Glitch settings
GLITCH_CHANCE    = 0.08      # chance of glitch per frame
GLITCH_INTENSITY = 6         # max pixel offset during glitch
FLICKER_CHANCE   = 0.04      # chance of full flicker per frame

# ── Background terminal settings
BG_COLS     = 12             # number of background columns

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

_F = {}

def _fonts():
    if not _F:
        _F["main"]   = font(MAIN_SIZE,   bold=True)
        _F["credit"] = font(CREDIT_SIZE, bold=True)
        _F["bg"]     = font(BG_SIZE)
    return _F

# ── TERMINAL BACKGROUND ───────────────────────────────────────
_BG_CHARS = list(string.ascii_letters + string.digits + "!@#$%^&*<>/?\\|[]{}=+-")
_BG_COLS  = []

def _init_bg(F):
    global _BG_COLS
    col_w  = W // BG_COLS
    _BG_COLS = []
    for i in range(BG_COLS):
        x = i * col_w + col_w // 2
        y = random.randint(-H, 0)
        _BG_COLS.append({"x": x, "chars": [{
            "char":  random.choice(_BG_CHARS),
            "y":     y + j * (BG_SIZE + 2),
            "alpha": random.randint(20, 80),
            "speed": random.uniform(0.4, 1.2),
        } for j in range(random.randint(4, 12))]})

def _update_bg():
    for col in _BG_COLS:
        for c in col["chars"]:
            c["y"] += c["speed"]
            if random.random() < 0.05:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in col["chars"]):
            y = random.randint(-H // 2, 0)
            col["chars"] = [{
                "char":  random.choice(_BG_CHARS),
                "y":     y + j * (BG_SIZE + 2),
                "alpha": random.randint(20, 80),
                "speed": random.uniform(0.4, 1.2),
            } for j in range(random.randint(4, 12))]

def _draw_bg(d, F):
    for col in _BG_COLS:
        for c in col["chars"]:
            if 0 <= c["y"] <= H:
                a = c["alpha"]
                d.text((col["x"], int(c["y"])),
                       c["char"], font=F["bg"], fill=(0, a, int(a * 1.5)))

# ── GLITCH ────────────────────────────────────────────────────
_glitch_active  = False
_glitch_timer   = 0.0
_glitch_offset  = (0, 0)
_glitch_color   = None
_flicker_active = False

def _update_glitch():
    global _glitch_active, _glitch_timer, _glitch_offset
    global _glitch_color, _flicker_active

    now = time.time()
    _flicker_active = random.random() < FLICKER_CHANCE

    if not _glitch_active:
        if random.random() < GLITCH_CHANCE:
            _glitch_active = True
            _glitch_timer  = now
            _glitch_offset = (
                random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY),
                random.randint(-2, 2)
            )
            _glitch_color = random.choice([
                (0,   220, 255),
                (200, 200, 255),
                (0,   100, 255),
            ])
    else:
        if now - _glitch_timer > random.uniform(0.05, 0.15):
            _glitch_active = False

# ── MAIN TEXT ─────────────────────────────────────────────────

def _draw_main(d, F):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    l1_w = tw(LINE1)
    l2_w = tw(LINE2)
    l1_h = th(LINE1)
    l2_h = th(LINE2)

    total_h = l1_h + LINE_GAP + l2_h

    # use TEXT_X and TEXT_Y to position the block
    # TEXT_X/Y of 0.5 = centered, 0.0 = top/left, 1.0 = bottom/right
    center_x = int(W * TEXT_X)
    center_y = int(H * TEXT_Y)

    l1_x = center_x - l1_w // 2
    l1_y = center_y - total_h // 2
    l2_x = center_x - l2_w // 2
    l2_y = l1_y + l1_h + LINE_GAP

    if _flicker_active:
        col1 = (0, 60, 120)
        col2 = (60, 60, 120)
    elif _glitch_active:
        col1 = _glitch_color
        col2 = _glitch_color
        l1_x += _glitch_offset[0]
        l1_y += _glitch_offset[1]
        l2_x += _glitch_offset[0]
        l2_y += _glitch_offset[1]
        ghost = (0, 30, 80)
        d.text((l1_x + 3, l1_y + 1), LINE1, font=F["main"], fill=ghost)
        d.text((l2_x - 3, l2_y - 1), LINE2, font=F["main"], fill=ghost)
    else:
        col1 = C["white"]
        col2 = C["blue"]

    # glow
    for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
        d.text((l1_x+ox, l1_y+oy), LINE1, font=F["main"], fill=(0, 20, 50))
        d.text((l2_x+ox, l2_y+oy), LINE2, font=F["main"], fill=(0, 20, 50))

    d.text((l1_x, l1_y), LINE1, font=F["main"], fill=col1)
    d.text((l2_x, l2_y), LINE2, font=F["main"], fill=col2)

    # underline under LINE2
    line_y   = l2_y + l2_h + 6
    line_col = _glitch_color if _glitch_active else C["dimblue"]
    d.line([(l2_x, line_y), (l2_x + l2_w, line_y)], fill=line_col, width=2)

def _draw_credit(d, F):
    cw = F["credit"].getbbox(CREDIT)[2]
    ch = F["credit"].getbbox(CREDIT)[3]
    cx = int(W * CREDIT_X) - cw
    cy = int(H * CREDIT_Y) - ch
    d.text((cx, cy), CREDIT, font=F["credit"], fill=C["dimblue"])

# ── MAIN DRAW ─────────────────────────────────────────────────
_tick      = 0
_bg_inited = False

def draw():
    global _tick, _bg_inited
    _tick += 1

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    _update_bg()
    _update_glitch()

    img, d = new_frame()
    draw_scanlines(d)
    _draw_bg(d, F)

    # glitch scan lines
    if _glitch_active and random.random() < 0.4:
        for _ in range(random.randint(1, 3)):
            gy   = random.randint(0, H)
            gx   = random.randint(0, W // 2)
            gw   = random.randint(20, 100)
            gcol = (0, random.randint(20, 80), random.randint(80, 180))
            d.line([(gx, gy), (gx + gw, gy)], fill=gcol, width=1)

    _draw_main(d, F)
    _draw_credit(d, F)

    push(img)

# ── STANDALONE ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running HELLO LOSER — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)