#!/usr/bin/env python3
"""
BearBox Network — Plug In Adapter Screen
Waits until TL-WN722N is detected.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, tplink_connected

def run():
    if tplink_connected():
        return

    F     = fonts()
    pulse = 0

    while not tplink_connected():
        pulse += 1
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "PLUG IN ADAPTER", "waiting for TL-WN722N")

        amp  = abs((pulse % 40) - 20) / 20.0
        col  = (0, int(100 + amp * 155), int(200 + amp * 55))

        for i, msg in enumerate(["Please plug in your", "TL-WN722N WiFi adapter"]):
            mw = F["body"].getbbox(msg)[2]
            c  = col if i == 1 else C["dimwhite"]
            d.text(((W - mw) // 2, 100 + i * 28), msg, font=F["body"], fill=c)

        # animated USB box
        bx, by, bw, bh = W // 2 - 30, 170, 60, 40
        d.rectangle([bx, by, bx + bw, by + bh], outline=col, fill=C["panel"])
        uw = F["small"].getbbox("USB")[2]
        d.text((bx + (bw - uw) // 2, by + 12), "USB", font=F["small"], fill=col)

        dots = "." * (1 + (pulse // 10) % 3)
        label = f"Waiting{dots}"
        lw    = F["big"].getbbox(label)[2]
        d.text(((W - lw) // 2, 228), label, font=F["big"], fill=C["dimblue"])

        push(img)
        time.sleep(1 / 10)
