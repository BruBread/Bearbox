#!/usr/bin/env python3
"""
BearBox Offline — WiFi Portal Screen
Shows AP name, IP address and portal URL instead of QR code.
No external dependencies.
"""

import os
import sys
import time
import math
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap

PORTAL_URL = "http://bearbox.local"
AP_SSID    = "BearBox-AP"
AP_IP      = "10.0.0.1"

R = {
    "bg":       (12,  0,   0),
    "panel":    (22,  0,   0),
    "red":      (255, 40,  40),
    "midred":   (180, 20,  20),
    "dimred":   (70,  0,   0),
    "darkred":  (25,  0,   0),
    "white":    (255, 220, 220),
    "dimwhite": (140, 80,  80),
}

_F = {}
def _fonts():
    if not _F:
        _F["title"]  = font(18, bold=True)
        _F["big"]    = font(28, bold=True)
        _F["body"]   = font(15, bold=True)
        _F["small"]  = font(12)
        _F["tiny"]   = font(10)
    return _F

_tick = 0

def draw():
    """
    Returns True  — tap detected, idle_offline should cycle
            None  — no tap this frame
    """
    global _tick
    _tick += 1

    F     = _fonts()
    pulse = (math.sin(time.time() * 2.0) + 1) / 2

    img, d = new_frame(bg=R["bg"])

    # scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))

    # ── header ────────────────────────────────────────────────
    HEADER_H = 48
    d.rectangle([0, 0, W, HEADER_H], fill=R["panel"])
    d.line([(0, HEADER_H), (W, HEADER_H)], fill=R["dimred"], width=1)

    title = "WIFI SETUP"
    tw    = F["title"].getbbox(title)[2]
    glow  = (int(120 + pulse * 60), 0, 0)
    for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        d.text(((W - tw) // 2 + ox, 8 + oy), title,
               font=F["title"], fill=glow)
    d.text(((W - tw) // 2, 8), title, font=F["title"], fill=R["red"])

    # ── step 1 ────────────────────────────────────────────────
    cy = HEADER_H + 18
    s1 = "1. Connect your device to:"
    s1w = F["small"].getbbox(s1)[2]
    d.text(((W - s1w) // 2, cy), s1, font=F["small"], fill=R["dimwhite"])
    cy += 20

    # AP name — big and bright
    apw = F["big"].getbbox(AP_SSID)[2]
    d.text(((W - apw) // 2, cy), AP_SSID, font=F["big"], fill=R["red"])
    cy += 38

    # ── step 2 ────────────────────────────────────────────────
    s2  = "2. Then open your browser and go to:"
    s2w = F["small"].getbbox(s2)[2]
    d.text(((W - s2w) // 2, cy), s2, font=F["small"], fill=R["dimwhite"])
    cy += 20

    # Portal URL — pulsing
    url_col = (int(160 + pulse * 95), int(pulse * 20), int(pulse * 20))
    uw = F["body"].getbbox(PORTAL_URL)[2]
    d.text(((W - uw) // 2, cy), PORTAL_URL, font=F["body"], fill=url_col)
    cy += 32

    # ── divider ───────────────────────────────────────────────
    d.line([(40, cy), (W - 40, cy)], fill=R["dimred"], width=1)
    cy += 10

    # ── or use IP directly ────────────────────────────────────
    alt  = "or use IP directly:"
    altw = F["tiny"].getbbox(alt)[2]
    d.text(((W - altw) // 2, cy), alt, font=F["tiny"], fill=R["dimred"])
    cy += 16

    ipw = F["body"].getbbox(AP_IP)[2]
    d.text(((W - ipw) // 2, cy), AP_IP, font=F["body"], fill=R["midred"])
    cy += 32

    # ── footer ────────────────────────────────────────────────
    footer_y = H - 26
    d.rectangle([0, footer_y, W, H], fill=R["panel"])
    d.line([(0, footer_y), (W, footer_y)], fill=R["dimred"], width=1)

    hint  = "tap to go back"
    hw    = F["tiny"].getbbox(hint)[2]
    d.text(((W - hw) // 2, footer_y + 7),
           hint, font=F["tiny"], fill=R["dimred"])

    push(img)

    if check_tap():
        return True
    return None


if __name__ == "__main__":
    print("Networks offline screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1 / 30)