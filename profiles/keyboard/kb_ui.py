#!/usr/bin/env python3
"""
BearBox — Keyboard Profile
Entry point: plays KEYBOARD CONNECTED screen then launches terminal.
"""

import os
import sys

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)


def run():
    from profiles.keyboard.screen_keyboard_connected import run as play_intro
    from profiles.keyboard.kb_terminal import run as launch_terminal

    play_intro()
    launch_terminal()


if __name__ == "__main__":
    run()
