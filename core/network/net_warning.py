#!/usr/bin/env python3
"""
BearBox Network — No Connection Warning Screen
Returns: "connect" or "offline"
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, draw_two_buttons, check_tap, tapped

def run():
    F     = fonts()
    pulse = 0

    # pre-calculate button positions
    btn_w  = 180
    btn_h  = 52
    btn_y  = H - btn_h - 20
    gap    = 16
    left_x  = (W // 2) - btn_w - gap // 2
    right_x = (W // 2) + gap // 2

    while True:
        pulse += 1
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "NO CONNECTION", "internet not detected", color=C["amber"])

        # pulsing ! icon
        amp   = abs((pulse % 60) - 30) / 30.0
        w_col = (255, int(100 + amp * 155), 0)
        iw    = font(52, bold=True).getbbox("!")[2]
        d.text(((W - iw) // 2, 54), "!", font=font(52, bold=True), fill=w_col)

        # message
        for i, msg in enumerate([
            "Device is not connected",
            "to the internet.",
            "Time may be out of sync.",
        ]):
            mw = F["body"].getbbox(msg)[2]
            d.text(((W - mw) // 2, 118 + i * 22), msg,
                   font=F["body"], fill=C["dimwhite"])

        d.line([(20, 196), (W - 20, 196)], fill=C["dimblue"], width=1)

        # sublabels above buttons
        d.text((left_x,  btn_y - 18), "scan & connect",
               font=F["small"], fill=C["dimwhite"])
        d.text((right_x, btn_y - 18), "continue anyway",
               font=F["small"], fill=C["dimwhite"])

        l_rect, r_rect = draw_two_buttons(
            d, F, "CONNECT", "GO OFFLINE", C["green"], C["red"]
        )

        push(img)

        if check_tap():
            if tapped(*l_rect):
                return "connect"
            if tapped(*r_rect):
                return "offline"

        time.sleep(1 / 30)
