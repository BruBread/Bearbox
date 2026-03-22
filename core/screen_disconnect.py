#!/usr/bin/env python3
"""
BearBox — Module Disconnected Screen
Red glitchy "MODULE DISCONNECTED" screen.
Plays when a profile is stopped, then fades into hello.py.
"""

import os
import sys
import time
import random
import string

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
LINE1            = "MODULE"
LINE2            = "DISCONNECTED"
MAIN_SIZE        = 56
DURATION         = 3.0      # total screen time before fading to hello
GLITCH_CHANCE    = 0.12     # higher = more glitchy
GLITCH_INTENSITY = 10
FLICKER_CHANCE   = 0.06

# ─────────────────────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────────────────────
C = {
    "bg":    (10, 0,  0),
    "red":   (255, 30, 30),
    "dimred":(120, 0,  0),
    "darkred":(40, 0,  0),
}

# ─────────────────────────────────────────────────────────────
# BG NOISE
# ─────────────────────────────────────────────────────────────
_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()
    def _reset(self):
        self.speed = random.uniform(1.5, 4.0)
        self.chars = [{"char": random.choice(_BG_CHARS),
                       "y":    random.randint(-H, 0) - i * 12}
                      for i in range(random.randint(4, 10))]
    def update(self):
        for c in self.chars:
            c["y"] += self.speed
            if random.random() < 0.06:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in self.chars):
            self._reset()
    def draw(self, d, fnt):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                d.text((self.x, y), c["char"], font=fnt, fill=(60, 0, 0))

# ─────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────
_F_MAIN   = None
_F_SMALL  = None
_BG_FONT  = None

def _init_fonts():
    global _F_MAIN, _F_SMALL, _BG_FONT
    def _font(size, bold=False):
        for name in ["DejaVu Sans Mono", "Courier New", "Courier"]:
            try:
                return font(size, bold=bold)
            except:
                pass
        return font(size)
    _F_MAIN  = font(MAIN_SIZE, bold=True)
    _F_SMALL = font(12)
    _BG_FONT = font(10)

# ─────────────────────────────────────────────────────────────
# GLITCH STATE
# ─────────────────────────────────────────────────────────────
_glitch_active   = False
_glitch_timer    = 0.0
_glitch_offset   = (0, 0)
_glitch_color    = None
_flicker_active  = False

def _update_glitch():
    global _glitch_active, _glitch_timer, _glitch_offset
    global _glitch_color, _flicker_active

    now = time.time()
    _flicker_active = random.random() < FLICKER_CHANCE

    if not _glitch_active:
        if random.random() < GLITCH_CHANCE:
            _glitch_active  = True
            _glitch_timer   = now
            _glitch_offset  = (
                random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY),
                random.randint(-2, 2)
            )
            _glitch_color = random.choice([
                (255, 0,   0),
                (200, 50,  50),
                (255, 80,  80),
            ])
    else:
        if now - _glitch_timer > random.uniform(0.04, 0.12):
            _glitch_active = False

# ─────────────────────────────────────────────────────────────
# DRAW TEXT
# ─────────────────────────────────────────────────────────────

def _draw_main(d, alpha=1.0):
    def tw(t): return _F_MAIN.getbbox(t)[2] - _F_MAIN.getbbox(t)[0]
    def th(t): return _F_MAIN.getbbox(t)[3] - _F_MAIN.getbbox(t)[1]

    l1_w = tw(LINE1)
    l2_w = tw(LINE2)
    l1_h = th(LINE1)
    l2_h = th(LINE2)
    gap  = 10

    total_h = l1_h + gap + l2_h
    l1_x    = (W - l1_w) // 2
    l1_y    = (H - total_h) // 2
    l2_x    = (W - l2_w) // 2
    l2_y    = l1_y + l1_h + gap

    a = int(255 * alpha)

    if _flicker_active:
        col1 = (int(a * 0.3), 0, 0)
        col2 = (int(a * 0.3), 0, 0)
    elif _glitch_active:
        col1 = (_glitch_color[0], int(_glitch_color[1]*alpha),
                int(_glitch_color[2]*alpha))
        col2 = col1
        l1_x += _glitch_offset[0]
        l1_y += _glitch_offset[1]
        l2_x += _glitch_offset[0]
        l2_y += _glitch_offset[1]
        # ghost shadow
        ghost = (int(a*0.15), 0, 0)
        d.text((l1_x + 4, l1_y + 1), LINE1, font=_F_MAIN, fill=ghost)
        d.text((l2_x - 4, l2_y - 1), LINE2, font=_F_MAIN, fill=ghost)
    else:
        col1 = (a, int(a*0.12), int(a*0.12))
        col2 = (a, int(a*0.12), int(a*0.12))

    # glow
    glow = (int(a*0.08), 0, 0)
    for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
        d.text((l1_x+ox, l1_y+oy), LINE1, font=_F_MAIN, fill=glow)
        d.text((l2_x+ox, l2_y+oy), LINE2, font=_F_MAIN, fill=glow)

    d.text((l1_x, l1_y), LINE1, font=_F_MAIN, fill=col1)
    d.text((l2_x, l2_y), LINE2, font=_F_MAIN, fill=col2)

    # underline
    line_y   = l2_y + l2_h + 6
    line_col = _glitch_color if _glitch_active else (int(a*0.4), 0, 0)
    d.line([(l2_x, line_y), (l2_x + l2_w, line_y)],
           fill=line_col, width=2)

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

_bg_cols = None

def run():
    global _bg_cols

    _init_fonts()

    if _bg_cols is None:
        _bg_cols = [_BgCol(int((i+0.5)*W/16)) for i in range(16)]

    start = time.time()

    while True:
        now      = time.time()
        elapsed  = now - start
        progress = elapsed / DURATION

        if progress >= 1.0:
            break

        # fade out in last 30%
        if progress > 0.7:
            alpha = 1.0 - (progress - 0.7) / 0.3
            alpha = max(0.0, alpha)
        else:
            alpha = 1.0

        _update_glitch()

        for col in _bg_cols:
            col.update()

        img, d = new_frame(bg=C["bg"])

        # scanlines
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(15, 0, 0))

        # bg noise
        for col in _bg_cols:
            col.draw(d, _BG_FONT)

        # horizontal glitch lines
        if _glitch_active and random.random() < 0.5:
            for _ in range(random.randint(1, 4)):
                gy   = random.randint(0, H)
                gx   = random.randint(0, W//2)
                gw   = random.randint(20, 120)
                gcol = (random.randint(100, 255), 0, 0)
                d.line([(gx, gy), (gx+gw, gy)], fill=gcol, width=1)

        _draw_main(d, alpha)

        push(img)
        time.sleep(1/30)

    # clear screen
    img, _ = new_frame(bg=(0, 0, 0))
    push(img)
    time.sleep(0.1)

    # fade into hello
    from core.idle.hello import draw as draw_hello
    hello_start = time.time()
    while time.time() - hello_start < 0.5:
        draw_hello()
        time.sleep(1/30)


if __name__ == "__main__":
    print("MODULE DISCONNECTED screen — Ctrl+C to stop")
    while True:
        run()
        time.sleep(1)
