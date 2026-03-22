#!/usr/bin/env python3
"""
BearBox — Idle Main Loop
Runs when no device is plugged in.
Cycles through idle screens on tap.
Saves time every 30 seconds so clock survives hard power cuts.

Screens (in order):
  0. clock
  1. hello
  2. matrix   ← uncomment when ready
  3. bear     ← uncomment when ready
"""

import os
import sys
import time
import threading
import select

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import W, H, FB_DEV

# ── import screens ────────────────────────────────────────────
from clock import draw as draw_clock
from hello import draw as draw_hello
# from matrix import draw as draw_matrix
from bear   import draw as draw_bear

SCREENS = [
    ("clock", draw_clock),
    ("hello", draw_hello),
    # ("matrix", draw_matrix),
    ("bear",   draw_bear),
]

# ── time save ─────────────────────────────────────────────────
TIME_FILE  = "/home/bearbox/bearbox/.last_time"
SAVE_EVERY = 30  # seconds

def _save_time_loop():
    """Periodically save current time to file."""
    while True:
        try:
            with open(TIME_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            print(f">> Time save failed: {e}")
        time.sleep(SAVE_EVERY)

# ── touch ─────────────────────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 1.2
_touch_fd    = None
_last_tap    = 0

def _check_tap():
    global _touch_fd, _last_tap
    if not os.path.exists(TOUCH_DEV):
        return False
    try:
        if _touch_fd is None:
            _touch_fd = open(TOUCH_DEV, "rb")
        r, _, _ = select.select([_touch_fd], [], [], 0)
        if r:
            while True:
                r2, _, _ = select.select([_touch_fd], [], [], 0)
                if not r2:
                    break
                _touch_fd.read(16)
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except:
        _touch_fd = None
    return False

# ── main loop ─────────────────────────────────────────────────

def run():
    # boot animation
    from boot_anim import play as play_boot
    play_boot()

    # network check + time restore
    from network.net_check import run as run_network
    run_network()

    # start periodic time saver
    threading.Thread(target=_save_time_loop, daemon=True).start()
    print(">> Time saver started — saving every 30s")

    current = 0
    print(f"BearBox idle started — tap to cycle screens")
    print(f"Current screen: {SCREENS[current][0]}")

    while True:
        SCREENS[current][1]()

        if _check_tap():
            current = (current + 1) % len(SCREENS)
            print(f">> Switched to: {SCREENS[current][0]}")

        time.sleep(1 / 30)

if __name__ == "__main__":
    run()
