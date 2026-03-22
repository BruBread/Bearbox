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

from boot_anim import play as play_boot
from network.net_check import run as run_network


SCREENS = [
    draw_clock,
    draw_hello,
    # draw_matrix,
    # draw_bear,
]

# ── touch input ───────────────────────────────────────────────
import select

_touch_fd = None

_touch_fd   = None
_last_tap   = 0
TAP_COOLDOWN = 1.2  # seconds — increase if still too sensitive

def _check_tap():
    global _touch_fd, _last_tap
    try:
        if _touch_fd is None:
            _touch_fd = open("/dev/input/event0", "rb")

        r, _, _ = select.select([_touch_fd], [], [], 0)
        if r:
            # drain ALL pending events so drag doesn't fire multiple times
            while True:
                r2, _, _ = select.select([_touch_fd], [], [], 0)
                if not r2:
                    break
                _touch_fd.read(16)

            # only register if cooldown has passed
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except:
        _touch_fd = None
    return False

# ── main loop ─────────────────────────────────────────────────

def run():
    play_boot()   # plays once, guard prevents double play
    run_network() #checks connection
    current = 0

    current = 0

    print("BearBox idle started — tap screen to cycle")

    while True:
        # draw current screen
        SCREENS[current]()

        # check for tap
        if _check_tap():
            current = (current + 1) % len(SCREENS)
            print(f"Switched to screen {current}")

        time.sleep(1/30)

if __name__ == "__main__":
    run()