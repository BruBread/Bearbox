#!/usr/bin/env python3
"""
BearBox Network — Network List Screen
Tap a network to select it. Returns SSID or None if back.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, draw_btn, check_tap, tapped, HOTSPOT_SSID

ROW_H   = 50
VISIBLE = (H - 60 - 40) // ROW_H  # leave room for back button

def run(networks):
    if not networks:
        return None

    F        = fonts()
    networks = sorted(networks, key=lambda s: 0 if s == HOTSPOT_SSID else 1)
    scroll   = 0

    # back button
    back_x, back_y, back_w, back_h = 8, H - 38, 90, 30

    while True:
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "SELECT NETWORK", f"{len(networks)} found")

        # network rows
        row_rects = []
        for i in range(VISIBLE):
            idx = i + scroll
            if idx >= len(networks):
                break
            ssid  = networks[idx]
            ry    = 52 + i * ROW_H
            is_hp = ssid == HOTSPOT_SSID

            bg  = (0, 20, 45) if is_hp else C["panel"]
            out = C["blue"]   if is_hp else C["dimblue"]
            d.rectangle([8, ry, W - 8, ry + ROW_H - 4], fill=bg, outline=out)

            if is_hp:
                tag = "● HOTSPOT"
                tw  = F["small"].getbbox(tag)[2]
                d.text((W - tw - 14, ry + 6), tag,
                       font=F["small"], fill=C["blue"])

            col = C["blue"] if is_hp else C["white"]
            d.text((16, ry + 15), ssid[:28], font=F["body"], fill=col)
            row_rects.append((8, ry, W - 16, ROW_H - 4, ssid))

        # scroll indicators
        if scroll > 0:
            d.text((W // 2 - 6, 48), "▲", font=F["small"], fill=C["dimblue"])
        if scroll + VISIBLE < len(networks):
            d.text((W // 2 - 6, H - 46), "▼", font=F["small"], fill=C["dimblue"])

        # back button
        draw_btn(d, F, back_x, back_y, back_w, back_h,
                 "◀ BACK", C["dimblue"], text_color=C["dimwhite"])

        push(img)

        if check_tap():
            # check back button
            if tapped(back_x, back_y, back_w, back_h):
                return None

            # check network rows
            for (rx, ry, rw, rh, ssid) in row_rects:
                if tapped(rx, ry, rw, rh):
                    return ssid

            # scroll down if tapped below visible rows
            if scroll + VISIBLE < len(networks):
                scroll += 1

        time.sleep(1 / 30)
