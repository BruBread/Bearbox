#!/usr/bin/env python3
"""
BearBox Network — Go Offline Screen
Animated typewriter warning. Tap CONTINUE to proceed.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, draw_btn, check_tap, tapped, wrap_text

WARNING = (
    "WARNING: Device is offline. "
    "Time may be out of sync and "
    "some features may not work "
    "correctly. Proceed with caution."
)
TYPE_SPEED = 0.04

def run():
    F         = fonts()
    start     = time.time()
    done      = False

    btn_w = 220
    btn_x = (W - btn_w) // 2
    btn_y = H - 50
    btn_h = 34

    while True:
        now    = time.time()
        char_i = min(int((now - start) / TYPE_SPEED), len(WARNING))
        typed  = WARNING[:char_i]

        if char_i >= len(WARNING):
            done = True

        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "GOING OFFLINE", "read carefully", color=C["red"])

        # warning panel
        panel_y = 52
        panel_h = btn_y - panel_y - 8 if done else H - panel_y - 10
        d.rectangle([10, panel_y, W - 10, panel_y + panel_h],
                    fill=(20, 0, 0), outline=C["red"])

        # typed text
        lines = wrap_text(typed, F["body"], W - 36)
        for i, line in enumerate(lines[:7]):
            d.text((18, panel_y + 10 + i * 20),
                   line, font=F["body"], fill=C["white"])

        # blinking cursor
        if not done or int(now * 2) % 2 == 0:
            if lines:
                lw = F["body"].getbbox(lines[-1])[2]
                ly = panel_y + 10 + (len(lines) - 1) * 20
                d.rectangle([18 + lw + 2, ly + 2, 18 + lw + 8, ly + 14],
                            fill=C["red"])

        # continue button after typing done
        if done:
            btn_rect = draw_btn(d, F, btn_x, btn_y, btn_w, btn_h,
                                "CONTINUE OFFLINE", C["red"], text_color=C["red"])
            push(img)
            if check_tap() and tapped(*btn_rect):
                return
        else:
            push(img)

        time.sleep(1 / 30)
