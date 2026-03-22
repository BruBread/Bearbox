#!/usr/bin/env python3
"""
BearBox AP — Kick Confirmation Popup
Returns True if user confirmed kick.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.."))
from display import new_frame, push, font, W, H
from profiles.wifi.ap.ap_utils import (
    C, fonts, draw_header, draw_btn,
    check_tap, tapped, draw_scanlines_pink, format_duration
)

def run(device):
    F     = fonts()
    pulse = 0

    btn_w  = 160
    btn_h  = 52
    btn_y  = H - btn_h - 20
    gap    = 20
    yes_x  = (W // 2) - btn_w - gap // 2
    no_x   = (W // 2) + gap // 2

    while True:
        pulse += 1
        img, d = new_frame(bg=C["bg"])
        draw_scanlines_pink(d)
        draw_header(d, F, "KICK DEVICE?", "confirm action")

        amp   = abs((pulse % 50) - 25) / 25.0
        w_col = (255, int(amp * 80), int(180 * amp))
        iw    = font(44, bold=True).getbbox("!")[2]
        d.text(((W - iw) // 2, 54), "!",
               font=font(44, bold=True), fill=w_col)

        d.rectangle([10, 110, W-10, 220], fill=C["panel"], outline=C["dimpurple"])

        for i, (label, val, col) in enumerate([
            ("HOST",      device["hostname"][:22],              C["white"]),
            ("IP",        device["ip"],                         C["pink"]),
            ("MAC",       device["mac"],                        C["dimwhite"]),
            ("CONNECTED", format_duration(device["connected"]), C["pink"]),
        ]):
            d.text((20,  118 + i * 24), label, font=F["small"], fill=C["dimpink"])
            d.text((110, 118 + i * 24), val,   font=F["small"], fill=col)

        d.line([(20, 228), (W-20, 228)], fill=C["dimpurple"], width=1)

        yes_rect = draw_btn(d, F, yes_x, btn_y, btn_w, btn_h,
                            "KICK", C["red"], text_color=C["red"])
        no_rect  = draw_btn(d, F, no_x,  btn_y, btn_w, btn_h,
                            "CANCEL", C["dimpink"], text_color=C["dimwhite"])

        push(img)

        if check_tap():
            if tapped(*yes_rect):
                return True
            if tapped(*no_rect):
                return False

        time.sleep(1 / 30)
