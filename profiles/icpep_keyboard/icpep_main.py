#!/usr/bin/env python3
"""
BearBox — ICPEP Keyboard Profile
Triggered only by the SiGma Micro "TRACER Gamma Ivory" keyboard
(USB ID 1c4f:0002) — separate from the generic USB keyboard profile.

Entry point: plays the "WELCOME TO ICPEP" intro, then shows robot
eyes that glare red and scowl every time ENTER is pressed.
"""

import os
import sys
import time

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)


def run():
    from profiles.icpep_keyboard.screen_icpep_intro import run as play_intro
    from profiles.icpep_keyboard import icpep_eyes as eyes
    from profiles.icpep_keyboard import cloud_bump
    from profiles.keyboard.kb_input import KeyboardReader

    play_intro()

    kb = KeyboardReader()
    if not kb.start():
        print("[icpep] no keyboard device found — eyes will idle only")

    # kb_input.py queues "ENTER" for both the initial press AND every OS-level
    # key-repeat event while the button stays held — fine for the terminal
    # profile (repeat is wanted there for held backspace/arrows), but here it
    # means a held or bouncy button fires anger_up()/cloud_bump.bump() once
    # per repeat tick instead of once per real press. Cooldown matches the
    # one counter/script.js already uses for the same reason on the browser side.
    COOLDOWN_S = 0.35
    last_press = 0.0

    while True:
        key = kb.get_char()
        while key is not None:
            if key == "ENTER":
                now = time.time()
                if now - last_press >= COOLDOWN_S:
                    last_press = now
                    eyes.anger_up()
                    cloud_bump.bump()
            key = kb.get_char()

        eyes.draw()
        time.sleep(1 / 30)


if __name__ == "__main__":
    run()
