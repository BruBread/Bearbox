#!/usr/bin/env python3
"""
BearBox — Idle Main Loop
Runs when no device is plugged in.
Cycles through idle screens on tap.

Screens (in order):
  0. clock      ← starts here
  1. hello      ← HELLO LOSERS
  2. matrix     ← falling code
  3. bear       ← animated bear
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import W, H, FB_DEV

# ── import all screens ────────────────────────────────────────
from clock import draw as draw_clock
from hello import draw as draw_hello
# from matrix import draw as draw_matrix   ← uncomment when ready
# from bear import draw as draw_bear       ← uncomment when ready

# ── screen order — add more as you build them ─────────────────
SCREENS = [
    draw_clock,
    draw_hello,
    # draw_matrix,
    # draw_bear,
]

# ── touch input ───────────────────────────────────────────────
import select

_touch_fd = None

def _check_tap():
    global _touch_fd
    try:
        if _touch_fd is None:
            _touch_fd = open("/dev/input/event0", "rb")
        r, _, _ = select.select([_touch_fd], [], [], 0)
        if r:
            _touch_fd.read(16)  # consume the event
            return True
    except:
        _touch_fd = None
    return False

# ── main loop ─────────────────────────────────────────────────

def run():
    current    = 0
    last_tap   = 0
    TAP_COOLDOWN = 0.5  # seconds between taps

    print("BearBox idle started — tap screen to cycle")

    while True:
        # draw current screen
        SCREENS[current]()

        # check for tap
        if _check_tap():
            now = time.time()
            if now - last_tap > TAP_COOLDOWN:
                current  = (current + 1) % len(SCREENS)
                last_tap = now
                print(f"Switched to screen {current}")

        time.sleep(1/30)

if __name__ == "__main__":
    run()