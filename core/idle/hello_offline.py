#!/usr/bin/env python3
"""
BearBox Idle — OFFLINE Screen
Red version of hello.py that says OFFLINE.
Shows when Pi has no internet connection.
"""

import os
import sys
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

LINE1            = "OFFLINE"
CREDIT           = "SSH: 10.0.0.1"
MAIN_SIZE        = 90
CREDIT_SIZE      = 16
BG_SIZE          = 10
TEXT_X           = 0.5
TEXT_Y           = 0.45
CREDIT_X         = 0.5
CREDIT_Y         = 0.78
GLITCH_CHANCE    = 0.10
GLITCH_INTENSITY = 6
FLICKER_CHANCE   = 0.05
BG_COLS          = 12

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

R = {
    "bg":      (12,  0,   0),
    "red":     (255, 40,  40),
    "midred":  (180, 20,  20),
    "dimred":  (70,  0,   0),
    "darkred": (25,  0,   0),
    "white":   (255, 220, 220),
}

_BG_CHARS = list(string.ascii_letters + string.digits + "!@#$%^&*<>/?\\|[]{}=+-")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()
    def _reset(self):
        self.speed = random.uniform(0.4, 1.2)
        self.chars = [{"char": random.choice(_BG_CHARS),
                       "y":    random.randint(-H, 0) - i * (BG_SIZE+2),
                       "alpha": random.randint(15, 50)}
                      for i in range(random.randint(4, 12))]
    def update(self):
        for c in self.chars:
            c["y"] += self.speed
            if random.random() < 0.05:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in self.chars):
            self._reset()
    def draw(self, d, fnt):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                a = c["alpha"]
                d.text((self.x, y), c["char"], font=fnt, fill=(a, 0, 0))

_F    = {}
_cols = None

def _fonts():
    if not _F:
        _F["main"]   = font(MAIN_SIZE,   bold=True)
        _F["credit"] = font(CREDIT_SIZE, bold=True)
        _F["bg"]     = font(BG_SIZE)
    return _F

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
                (255, 0,   0),
                (220, 60,  60),
                (255, 100, 100),
            ])
    else:
        if now - _glitch_timer > random.uniform(0.05, 0.15):
            _glitch_active = False

def _draw_main(d, F):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    lw = tw(LINE1)
    lh = th(LINE1)
    lx = int(W * TEXT_X) - lw // 2
    ly = int(H * TEXT_Y) - lh // 2

    if _flicker_active:
        col = (50, 0, 0)
    elif _glitch_active:
        col = _glitch_color
        lx += _glitch_offset[0]
        ly += _glitch_offset[1]
        ghost = (30, 0, 0)
        d.text((lx+3, ly+1), LINE1, font=F["main"], fill=ghost)
        d.text((lx-3, ly-1), LINE1, font=F["main"], fill=ghost)
    else:
        col = R["red"]

    # glow
    for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
        d.text((lx+ox, ly+oy), LINE1, font=F["main"], fill=R["darkred"])

    d.text((lx, ly), LINE1, font=F["main"], fill=col)

    # underline
    line_y   = ly + lh + 6
    line_col = _glitch_color if _glitch_active else R["dimred"]
    d.line([(lx, line_y), (lx+lw, line_y)], fill=line_col, width=2)

def _draw_credit(d, F):
    cw = F["credit"].getbbox(CREDIT)[2]
    ch = F["credit"].getbbox(CREDIT)[3]
    cx = int(W * CREDIT_X) - cw // 2
    cy = int(H * CREDIT_Y) - ch // 2
    # background pill
    d.rectangle([cx-8, cy-4, cx+cw+8, cy+ch+4],
                fill=R["darkred"], outline=R["dimred"])
    d.text((cx, cy), CREDIT, font=F["credit"], fill=R["midred"])

_tick      = 0
_bg_inited = False

def draw():
    global _tick, _bg_inited, _cols
    _tick += 1

    F = _fonts()
    if not _bg_inited:
        col_w  = W // BG_COLS
        _cols  = [_BgCol(i * col_w + col_w//2) for i in range(BG_COLS)]
        _bg_inited = True

    _update_glitch()
    for col in _cols:
        col.update()

    img, d = new_frame(bg=R["bg"])

    # red scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))

    for col in _cols:
        col.draw(d, F["bg"])

    # glitch scan lines
    if _glitch_active and random.random() < 0.4:
        for _ in range(random.randint(1, 3)):
            gy   = random.randint(0, H)
            gx   = random.randint(0, W//2)
            gw   = random.randint(20, 100)
            gcol = (random.randint(100, 255), 0, 0)
            d.line([(gx, gy), (gx+gw, gy)], fill=gcol, width=1)

    _draw_main(d, F)
    _draw_credit(d, F)

    push(img)

if __name__ == "__main__":
    print("Offline screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)
