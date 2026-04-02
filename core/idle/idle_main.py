#!/usr/bin/env python3
"""
BearBox — Idle Main Loop
Runs when no device is plugged in.
Cycles through idle screens on tap.
Saves time every 30 seconds.
Checks internet every 30 seconds — if lost plays DISCONNECTED screen.

Boot sequence (first run only):
  - boot animation and net_check run concurrently in separate threads
  - a threading.Event signals the animation to exit early the moment
    net_check knows the result, cutting boot time significantly
  - animation always plays for at least MIN_DURATION seconds so it
    never just flickers on and off

Set env BB_SKIP_BOOT_ANIM=1 to skip the animation (e.g. returning from
a keyboard profile).  net_check still runs in that case.
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
import hello as hello_module
from bear  import draw as draw_bear
# from matrix import draw as draw_matrix

SCREENS = [
    ("clock", draw_clock),
    ("hello", hello_module.draw),
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
CHECK_EVERY = 30  # seconds between periodic internet checks

def _is_connected():
    from network.net_utils import is_connected
    return is_connected()

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
    except Exception:
        _touch_fd = None
    return False

# ── boot sequence ─────────────────────────────────────────────

def _run_boot():
    """
    Run boot animation and net_check concurrently.

    The animation accepts a threading.Event and will exit early (with a
    quick fade) once the event is set.  net_check sets it the moment it
    knows the network outcome.

    If BB_SKIP_BOOT_ANIM is set we still run net_check, just without
    the animation thread.
    """
    skip_boot = os.environ.get("BB_SKIP_BOOT_ANIM") == "1"

    # BB_SKIP_NET_CHECK is set when returning from idle_offline after
    # reconnecting so we don't immediately go offline again.
    skip_net = os.environ.get("BB_SKIP_NET_CHECK") == "1"
    if skip_net:
        print(">> Skipping net_check (already connected)")
        os.environ.pop("BB_SKIP_NET_CHECK", None)

    if skip_boot:
        print(">> Skipping boot animation (returning from profile)")
        if not skip_net:
            from network.net_check import run as run_network
            run_network()
        return

    # Both animation and net_check will run — link them with an event.
    done_event = threading.Event()

    def _net_thread():
        if skip_net:
            done_event.set()
            return
        from network.net_check import run as run_network
        run_network(done_event)

    net_t = threading.Thread(target=_net_thread, daemon=True)
    net_t.start()

    # Boot animation runs on the main thread so it owns the display.
    # It exits early once done_event is set (and MIN_DURATION has passed).
    from boot_anim import play as play_boot
    play_boot(done_event)

    # Wait for net_check to fully finish before we proceed
    # (it may still be showing the CONNECTED screen, etc.)
    net_t.join()

# ── main loop ─────────────────────────────────────────────────

def run():
    _run_boot()

    # Start background time saver
    threading.Thread(target=_save_time_loop, daemon=True).start()
    print(">> Time saver started")

    current    = 0
    last_check = time.time()

    print(f"BearBox idle — tap to cycle | screen: {SCREENS[current][0]}")

    while True:
        SCREENS[current][1]()

        if _check_tap():
            # reset hello state when cycling away from it
            if SCREENS[current][0] == "hello":
                hello_module.reset()
            current = (current + 1) % len(SCREENS)
            print(f">> Switched to: {SCREENS[current][0]}")



        # Periodic internet check
        if time.time() - last_check > CHECK_EVERY:
            last_check = time.time()
            from network.net_utils import has_internet
            if not has_internet():
                print(">> Internet lost — going offline")
                from screen_disconnected import run as play_disconnected
                play_disconnected()
                # Hand off to offline mode via subprocess so we don't grow
                # the call stack on every reconnect/disconnect cycle.
                os.execv(
                    sys.executable,
                    [sys.executable,
                     os.path.join(os.path.dirname(os.path.abspath(__file__)), "idle_offline.py")]
                )
                # execv replaces this process — code below never runs
                return

        time.sleep(1 / 30)


if __name__ == "__main__":
    run()
