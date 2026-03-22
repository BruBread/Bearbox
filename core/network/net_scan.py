#!/usr/bin/env python3
"""
BearBox Network — Scanning Screen
10 second animated scan. Returns list of SSIDs.
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, get_interface, run_cmd

SCAN_DURATION = 10

def run():
    F       = fonts()
    results = []
    done    = [False]

    def _scan():
        iface = get_interface()
        run_cmd(f"sudo ip link set {iface} up")
        out = run_cmd(f"sudo iwlist {iface} scan 2>/dev/null | grep ESSID")
        for line in out.split("\n"):
            if "ESSID" in line and '"' in line:
                ssid = line.split('"')[1]
                if ssid and ssid not in results:
                    results.append(ssid)
        done[0] = True

    threading.Thread(target=_scan, daemon=True).start()
    start = time.time()

    while not done[0]:
        elapsed  = time.time() - start
        progress = min(elapsed / SCAN_DURATION, 1.0)

        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "SCANNING", "searching for networks...")

        # spinner
        t    = int(time.time() * 4) % 4
        spin = ["◐", "◓", "◑", "◒"][t]
        sw   = font(36, bold=True).getbbox(spin)[2]
        d.text(((W - sw) // 2, 58), spin, font=font(36, bold=True), fill=C["blue"])

        # progress bar
        bar_x, bar_y = 30, H // 2 - 8
        bar_w, bar_h = W - 60, 16
        d.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                    fill=C["dim"], outline=C["dimblue"])
        filled = int(bar_w * progress)
        if filled > 0:
            d.rectangle([bar_x, bar_y, bar_x + filled, bar_y + bar_h],
                        fill=C["midblue"])
            head = min(20, filled)
            d.rectangle([bar_x + filled - head, bar_y,
                         bar_x + filled, bar_y + bar_h], fill=C["blue"])

        # percentage
        pct = f"{int(progress * 100)}%"
        pw  = F["big"].getbbox(pct)[2]
        d.text(((W - pw) // 2, bar_y + bar_h + 12), pct,
               font=F["big"], fill=C["blue"])

        found = f"Found {len(results)} network(s)..."
        fw    = F["small"].getbbox(found)[2]
        d.text(((W - fw) // 2, bar_y + bar_h + 36), found,
               font=F["small"], fill=C["dimwhite"])

        push(img)
        time.sleep(1 / 30)

    return results
