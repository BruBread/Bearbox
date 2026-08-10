#!/usr/bin/env python3
"""
BearBox — ICPEP Keyboard Intro Screen
"WELCOME TO ICPEP" glitch-resolve in blue and white.
Plays once when the SiGma Micro keyboard is detected, then hands off
to the robot-eyes screen.
"""

import os
import sys
import time
import math
import random
import string

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H

DURATION      = 3.0
LINE1         = "WELCOME TO"
LINE2         = "ICPEP"
LINE1_SIZE    = 44
LINE2_SIZE    = 96
LINE_GAP      = 10

BLUE          = (0,   180, 255)
WHITE         = (255, 255, 255)
SHADOW        = (0,   10,  25)
BG            = (0,   5,   15)
GLITCH_CHARS  = list(string.ascii_uppercase + string.digits + "@#$%&!?|/<>[]")


def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def run():
    F1 = font(LINE1_SIZE, bold=True)
    F2 = font(LINE2_SIZE, bold=True)

    lh1 = F1.getbbox(LINE1)[3]
    lh2 = F2.getbbox(LINE2)[3]
    total_h = lh1 + LINE_GAP + lh2
    y1 = H // 2 - total_h // 2
    y2 = y1 + lh1 + LINE_GAP

    start = time.time()

    while True:
        now = time.time()
        t   = now - start
        if t >= DURATION:
            break

        img, d = new_frame(bg=BG)

        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(0, 8, 18))

        resolved = min(1.0, (t / (DURATION * 0.7)) ** 0.5)
        pulse    = (1 + math.sin(t * 6)) / 2

        for text, fnt, y, base_color in (
            (LINE1, F1, y1, WHITE),
            (LINE2, F2, y2, BLUE),
        ):
            display = ""
            for i, ch in enumerate(text):
                if ch == " ":
                    display += " "
                    continue
                char_r = max(0.0, resolved - (i / len(text)) * 0.35)
                display += ch if random.random() < char_r else random.choice(GLITCH_CHARS)

            tw = fnt.getbbox(display)[2]
            x  = (W - tw) // 2

            col = _lerp_color(base_color, WHITE, pulse * 0.25 * resolved)
            d.text((x + 2, y + 2), display, font=fnt, fill=SHADOW)
            d.text((x, y), display, font=fnt, fill=col)

        push(img)
        time.sleep(1 / 30)

    # hold on the fully-resolved final frame
    img, d = new_frame(bg=BG)
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))
    for text, fnt, y, base_color in (
        (LINE1, F1, y1, WHITE),
        (LINE2, F2, y2, BLUE),
    ):
        tw = fnt.getbbox(text)[2]
        x  = (W - tw) // 2
        d.text((x + 2, y + 2), text, font=fnt, fill=SHADOW)
        d.text((x, y), text, font=fnt, fill=base_color)
    push(img)
    time.sleep(0.8)


if __name__ == "__main__":
    run()
