#!/usr/bin/env python3
"""
BearBox — Idle Main Loop
Runs when no device is plugged in.
Cycles through idle screens on tap.
Saves time every 30 seconds.
Checks internet every 30 seconds — if lost plays DISCONNECTED screen.

Set env BB_SKIP_BOOT_ANIM=1 to skip the boot animation (e.g. returning from keyboard).
"""

import os
import sys
import time
import threading
import select
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ── import screens ────────────────────────────────────────────
from clock import draw as draw_clock
from hello import draw as draw_hello
from bear  import draw as draw_bear
# from matrix import draw as draw_matrix

SCREENS = [
    ("clock", draw_clock),
    ("hello", draw_hello),
    ("bear",  draw_bear),
    # ("matrix", draw_matrix),
]

# ── time save ─────────────────────────────────────────────────
TIME_FILE  = "/home/bearbox/bearbox/.last_time"
SAVE_EVERY = 30

def _save_time_loop():
    while True:
        try:
            with open(TIME_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            print(f">> Time save failed: {e}")
        time.sleep(SAVE_EVERY)

# ── internet check ────────────────────────────────────────────
CHECK_EVERY = 30  # seconds between internet checks

def _is_connected():
    r = subprocess.run("ping -c 1 -W 2 8.8.8.8", shell=True, capture_output=True)
    return r.returncode == 0

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
    skip_boot = os.environ.get("BB_SKIP_BOOT_ANIM") == "1"

    if not skip_boot:
        from boot_anim import play as play_boot
        play_boot()
    else:
        print(">> Skipping boot animation (returning from profile)")

    # network check + time restore
    from network.net_check import run as run_network
    run_network()

    # start time saver
    threading.Thread(target=_save_time_loop, daemon=True).start()
    print(">> Time saver started")

    current    = 0
    last_check = time.time()

    print(f"BearBox idle — tap to cycle | screen: {SCREENS[current][0]}")

    while True:
        SCREENS[current][1]()

        if _check_tap():
            current = (current + 1) % len(SCREENS)
            print(f">> Switched to: {SCREENS[current][0]}")

        # check internet periodically
        if time.time() - last_check > CHECK_EVERY:
            last_check = time.time()
            if not _is_connected():
                print(">> Internet lost!")
                from screen_disconnected import run as play_disconnected
                play_disconnected()
                subprocess.run("sudo systemctl restart bearbox", shell=True)
                return

        time.sleep(1/30)

if __name__ == "__main__":
    run()