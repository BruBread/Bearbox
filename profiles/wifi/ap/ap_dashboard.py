#!/usr/bin/env python3
"""BearBox AP — Main Dashboard"""

import os, sys, time, threading

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H
from profiles.wifi.ap.ap_utils import (
    C, fonts, draw_header, draw_btn, draw_scanlines_pink,
    check_tap, tapped, get_connected_devices,
    get_ap_ip, kick_device, format_duration, run_cmd
)

ROW_H   = 56
VISIBLE = (H - 76 - 30) // ROW_H
_devices = []
_pulse   = 0

def _refresh_loop():
    global _devices
    while True:
        _devices = get_connected_devices()
        time.sleep(3)

threading.Thread(target=_refresh_loop, daemon=True).start()

def run():
    global _pulse
    F      = fonts()
    scroll = 0

    while True:
        _pulse += 1
        img, d = new_frame(bg=C["bg"])
        draw_scanlines_pink(d)
        draw_header(d, F, "SIPHON", "access point active")

        # status bar
        d.rectangle([0, 44, W, 72], fill=C["panel"])
        d.line([(0, 72), (W, 72)], fill=C["dimpurple"], width=1)
        ap_ip = get_ap_ip()
        count = len(_devices)
        d.text((10, 52), f"IP: {ap_ip}", font=F["small"], fill=C["pink"])
        amp     = abs((_pulse % 40) - 20) / 20.0
        dot_col = (int(255*amp), 0, int(180*amp))
        d.ellipse([W//2-30, 55, W//2-20, 65], fill=dot_col)
        cnt = f"{count} device{'s' if count != 1 else ''}"
        d.text((W//2-14, 52), cnt, font=F["small"], fill=C["white"])
        uptime = run_cmd("uptime -p 2>/dev/null | sed 's/up //'")
        uw     = F["small"].getbbox(uptime[:14])[2]
        d.text((W-uw-8, 52), uptime[:14], font=F["small"], fill=C["dimpink"])

        # device rows
        row_rects = []
        if not _devices:
            msg = "No devices connected"
            mw  = F["body"].getbbox(msg)[2]
            d.text(((W-mw)//2, H//2-10), msg, font=F["body"], fill=C["dimpink"])
        else:
            for i in range(VISIBLE):
                idx = i + scroll
                if idx >= len(_devices): break
                dev = _devices[idx]
                ry  = 78 + i * ROW_H
                d.rectangle([8, ry, W-8, ry+ROW_H-4],
                            fill=C["panel"], outline=C["dimpurple"])
                d.text((16, ry+6),  dev["hostname"][:20], font=F["body"],  fill=C["white"])
                d.text((16, ry+24), dev["ip"],             font=F["small"], fill=C["pink"])
                dur = format_duration(dev["connected"])
                dw  = F["small"].getbbox(dur)[2]
                d.text((W-dw-68, ry+6), dur, font=F["small"], fill=C["dimwhite"])
                kick_rect = draw_btn(d, F, W-62, ry+10, 52, 32,
                                     "KICK", C["red"], text_color=C["red"])
                row_rects.append((dev, kick_rect))
            if scroll > 0:
                d.text((W//2-6, 74), "▲", font=F["small"], fill=C["dimpurple"])
            if scroll + VISIBLE < len(_devices):
                d.text((W//2-6, H-20), "▼", font=F["small"], fill=C["dimpurple"])

        # footer
        d.rectangle([0, H-24, W, H], fill=C["panel"])
        d.line([(0, H-24), (W, H-24)], fill=C["dimpurple"], width=1)
        hint = "TAP KICK to remove a device"
        hw   = F["small"].getbbox(hint)[2]
        d.text(((W-hw)//2, H-16), hint, font=F["small"], fill=C["dimpurple"])
        push(img)

        if check_tap():
            for dev, krect in row_rects:
                if tapped(*krect):
                    from profiles.wifi.ap.ap_kick import run as show_kick
                    if show_kick(dev):
                        kick_device(dev["mac"])
                        img2, d2 = new_frame(bg=C["bg"])
                        draw_scanlines_pink(d2)
                        draw_header(d2, F, "KICKED!", dev["hostname"])
                        msg = f"{dev['ip']} removed"
                        mw  = F["body"].getbbox(msg)[2]
                        d2.text(((W-mw)//2, H//2-10), msg,
                               font=F["body"], fill=C["red"])
                        push(img2)
                        time.sleep(1.5)
                    break

        time.sleep(1/30)
