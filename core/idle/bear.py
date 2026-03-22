#!/usr/bin/env python3
"""
BearBox Idle — Robot Eyes (Cozmo-style)
Two cyan rounded squares that move around the screen.
Snappy blink by squishing height.
No pupils — the whole eye IS the expression.
"""

import os
import sys
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, C, W, H

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

EYE_W         = 100     # eye width
EYE_H         = 90      # eye height
EYE_RADIUS    = 24      # corner roundness
EYE_GAP       = 40      # gap between the two eyes
EYE_COLOR     = (0, 220, 255)    # cyan
BG_COLOR      = (0,   5,  15)    # dark background

# How far eyes drift from center
DRIFT_X       = 60      # max horizontal drift from center
DRIFT_Y       = 40      # max vertical drift from center

# Timing
LOOK_MOVE_T   = 0.25    # seconds to slide to new position
LOOK_MIN      = 0.6     # min seconds between moves
LOOK_MAX      = 2.5     # max seconds between moves

BLINK_CLOSE_T = 0.05    # snappy close
BLINK_HOLD_T  = 0.04    # held closed
BLINK_OPEN_T  = 0.09    # slightly slower open
BLINK_MIN     = 2.0
BLINK_MAX     = 5.5

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

# base center positions
_base_left_cx  = W // 2 - EYE_GAP // 2 - EYE_W // 2
_base_right_cx = W // 2 + EYE_GAP // 2 + EYE_W // 2
_base_cy       = H // 2

# current positions
_cur_ox  = 0.0   # current offset x (applied to both eyes)
_cur_oy  = 0.0   # current offset y
_tgt_ox  = 0.0   # target offset x
_tgt_oy  = 0.0   # target offset y
_look_t  = 0.0
_looking = False
_next_look = time.time() + random.uniform(LOOK_MIN, LOOK_MAX)

# blink
_blink      = "open"
_blink_t    = 0.0
_blink_h    = 1.0
_next_blink = time.time() + random.uniform(BLINK_MIN, BLINK_MAX)

_last_t = time.time()

def _update(dt):
    global _cur_ox, _cur_oy, _tgt_ox, _tgt_oy
    global _look_t, _looking, _next_look
    global _blink, _blink_t, _blink_h, _next_blink

    # ── movement ──────────────────────────────────────────────
    if not _looking:
        if time.time() >= _next_look:
            _looking = True
            _look_t  = 0.0
            _tgt_ox  = random.uniform(-1.0, 1.0)
            _tgt_oy  = random.uniform(-1.0, 1.0)
    else:
        _look_t += dt / LOOK_MOVE_T
        t = min(_look_t, 1.0)
        # smooth ease in-out
        t = t * t * (3 - 2 * t)
        _cur_ox += (_tgt_ox - _cur_ox) * t * 0.15
        _cur_oy += (_tgt_oy - _cur_oy) * t * 0.15
        if _look_t >= 1.0:
            _looking   = False
            _next_look = time.time() + random.uniform(LOOK_MIN, LOOK_MAX)

    # ── blink ─────────────────────────────────────────────────
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

def _draw_eye(d, base_cx):
    # apply drift offset
    cx = base_cx + int(_cur_ox * DRIFT_X)
    cy = _base_cy + int(_cur_oy * DRIFT_Y)

    # squish height for blink
    h  = max(4, int(EYE_H * _blink_h))
    w  = EYE_W
    r  = min(EYE_RADIUS, h // 2)

    x  = cx - w // 2
    y  = cy - h // 2

    d.rounded_rectangle([x, y, x + w, y + h],
                         radius=r,
                         fill=EYE_COLOR)

def draw():
    global _last_t
    now     = time.time()
    dt      = now - _last_t
    _last_t = now

    _update(dt)

    img, d = new_frame(bg=BG_COLOR)

    # scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    _draw_eye(d, _base_left_cx)
    _draw_eye(d, _base_right_cx)

    push(img)

if __name__ == "__main__":
    print("Robot eyes — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1 / 30)