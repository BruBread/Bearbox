#!/usr/bin/env python3
"""
BearBox — ICPEP Robot Eyes
Cozmo-style eyes (no mouth) for the ICPEP keyboard profile.
Calm and blue by default — call anger_up() once per ENTER press and
the eyes glare red and narrow into an angry scowl, then calm back
down over time.
"""

import os
import sys
import time
import random

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, W, H

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

EYE_W        = 100     # eye width
EYE_H        = 90      # eye height
EYE_RADIUS   = 24      # corner roundness
EYE_GAP      = 40      # gap between the two eyes
CALM_COLOR   = (0,   180, 255)   # blue — resting state
ANGRY_COLOR  = (255, 20,  20)    # red — mad state
BG_COLOR     = (0,   5,   15)

# How far eyes drift from center
DRIFT_X      = 60
DRIFT_Y      = 40

# Timing
LOOK_MOVE_T  = 0.25
LOOK_MIN     = 0.6
LOOK_MAX     = 2.5

BLINK_CLOSE_T = 0.05
BLINK_HOLD_T  = 0.04
BLINK_OPEN_T  = 0.09
BLINK_MIN     = 2.0
BLINK_MAX     = 5.5

# Anger — bumped by anger_up(), decays back to calm on its own
ANGER_PER_HIT = 0.45    # how mad one ENTER press makes it
ANGER_DECAY   = 0.12    # per second — how fast it calms back down
ANGER_SLANT   = 30      # px the inner-top corner is carved down at full anger

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

_base_left_cx  = W // 2 - EYE_GAP // 2 - EYE_W // 2
_base_right_cx = W // 2 + EYE_GAP // 2 + EYE_W // 2
_base_cy       = H // 2

_cur_ox  = 0.0
_cur_oy  = 0.0
_tgt_ox  = 0.0
_tgt_oy  = 0.0
_look_t  = 0.0
_looking = False
_next_look = time.time() + random.uniform(LOOK_MIN, LOOK_MAX)

_blink      = "open"
_blink_t    = 0.0
_blink_h    = 1.0
_next_blink = time.time() + random.uniform(BLINK_MIN, BLINK_MAX)

_anger  = 0.0
_last_t = time.time()


def anger_up():
    """Call once per ENTER press — bumps the anger level toward max."""
    global _anger
    _anger = min(1.0, _anger + ANGER_PER_HIT)


def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _update(dt):
    global _cur_ox, _cur_oy, _tgt_ox, _tgt_oy
    global _look_t, _looking, _next_look
    global _blink, _blink_t, _blink_h, _next_blink
    global _anger

    if not _looking:
        if time.time() >= _next_look:
            _looking = True
            _look_t  = 0.0
            _tgt_ox  = random.uniform(-1.0, 1.0)
            _tgt_oy  = random.uniform(-1.0, 1.0)
    else:
        _look_t += dt / LOOK_MOVE_T
        t = min(_look_t, 1.0)
        t = t * t * (3 - 2 * t)
        _cur_ox += (_tgt_ox - _cur_ox) * t * 0.15
        _cur_oy += (_tgt_oy - _cur_oy) * t * 0.15
        if _look_t >= 1.0:
            _looking   = False
            _next_look = time.time() + random.uniform(LOOK_MIN, LOOK_MAX)

    if _blink == "open":
        if time.time() >= _next_blink:
            _blink   = "closing"
            _blink_t = 0.0
    elif _blink == "closing":
        _blink_t += dt / BLINK_CLOSE_T
        _blink_h  = max(0.0, 1.0 - _blink_t)
        if _blink_t >= 1.0:
            _blink   = "closed"
            _blink_t = 0.0
            _blink_h = 0.0
    elif _blink == "closed":
        _blink_t += dt / BLINK_HOLD_T
        if _blink_t >= 1.0:
            _blink   = "opening"
            _blink_t = 0.0
    elif _blink == "opening":
        _blink_t += dt / BLINK_OPEN_T
        _blink_h  = min(1.0, _blink_t)
        if _blink_t >= 1.0:
            _blink      = "open"
            _blink_h    = 1.0
            _next_blink = time.time() + random.uniform(BLINK_MIN, BLINK_MAX)

    _anger = max(0.0, _anger - ANGER_DECAY * dt)


def _draw_eye(d, base_cx, side):
    cx = base_cx + int(_cur_ox * DRIFT_X)
    cy = _base_cy + int(_cur_oy * DRIFT_Y)

    h = max(4, int(EYE_H * _blink_h))
    w = EYE_W
    r = min(EYE_RADIUS, h // 2)

    x = cx - w // 2
    y = cy - h // 2

    color = _lerp_color(CALM_COLOR, ANGRY_COLOR, _anger)
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=color)

    # angry scowl: carve the inner-top corner down, slanting toward
    # the other eye like furrowed eyebrows
    slant = int(ANGER_SLANT * _anger)
    if slant > 1:
        half = w * 0.55
        if side == "left":
            inner_x = x + w
            cut = [(inner_x - half, y), (inner_x, y), (inner_x, y + slant)]
        else:
            inner_x = x
            cut = [(inner_x, y), (inner_x + half, y), (inner_x, y + slant)]
        d.polygon(cut, fill=BG_COLOR)


def draw():
    """Advance the eye animation one frame and push it to the display."""
    global _last_t
    now     = time.time()
    dt      = now - _last_t
    _last_t = now

    _update(dt)

    img, d = new_frame(bg=BG_COLOR)
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    _draw_eye(d, _base_left_cx,  "left")
    _draw_eye(d, _base_right_cx, "right")

    push(img)


if __name__ == "__main__":
    print("ICPEP eyes — Ctrl+C to stop, press Enter to make it mad")
    import threading

    def _watch_stdin():
        while True:
            input()
            anger_up()

    threading.Thread(target=_watch_stdin, daemon=True).start()
    while True:
        draw()
        time.sleep(1 / 30)
