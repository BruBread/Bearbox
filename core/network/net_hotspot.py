#!/usr/bin/env python3
"""
BearBox Network — Personal Hotspot Found Popup
Returns True = connect, False = skip.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import (
    fonts, draw_header, draw_btn, check_tap, tapped, HOTSPOT_SSID
)

def run():
    F      = fonts()
    pulse  = 0

    btn_w  = 160
    btn_h  = 52
    btn_y  = H - btn_h - 20
    gap    = 20
    yes_x  = (W // 2) - btn_w - gap // 2
    no_x   = (W // 2) + gap // 2

    while True:
        pulse += 1
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "HOTSPOT FOUND",
                    "personal hotspot detected", color=C["blue"])

        # pulsing icon
        amp = abs((pulse % 50) - 25) / 25.0
        col = (0, int(140 + amp * 115), int(200 + amp * 55))
        iw  = font(40).getbbox("()")[2]
        d.text(((W - 40) // 2, 54), "()", font=font(40), fill=col)

        # message
        for i, (msg, c) in enumerate([
            ("Personal Hotspot",           C["dimwhite"]),
            (f'"{HOTSPOT_SSID}"',          C["blue"]),
            ("was found nearby.",          C["dimwhite"]),
            ("Would you like to connect?", C["dimwhite"]),
        ]):
            mw = F["body"].getbbox(msg)[2]
            d.text(((W - mw) // 2, 108 + i * 22), msg, font=F["body"], fill=c)

        d.line([(20, 200), (W - 20, 200)], fill=C["dimblue"], width=1)

        yes_rect = draw_btn(d, F, yes_x, btn_y, btn_w, btn_h,
                            "YES", C["green"], text_color=C["green"])
        no_rect  = draw_btn(d, F, no_x,  btn_y, btn_w, btn_h,
                            "NO",  C["red"],   text_color=C["red"])

        push(img)

        if check_tap():
            if tapped(*yes_rect):
                return True
            if tapped(*no_rect):
                return False

        time.sleep(1 / 30)
