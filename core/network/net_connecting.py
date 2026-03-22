#!/usr/bin/env python3
"""
BearBox Network — Connecting Screen
10 second timeout. Shows countdown. Returns True if connected.
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import (
    fonts, draw_header, run_cmd,
    get_interface, is_connected, sync_time
)

TIMEOUT = 10  # seconds before giving up

def _connect(ssid, password, result):
    iface    = get_interface()
    psk_line = ('psk="' + password + '"') if password else "key_mgmt=NONE"
    wpa      = f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
network={{
    ssid="{ssid}"
    {psk_line}
}}
"""
    with open("/tmp/bb_wpa.conf", "w") as f:
        f.write(wpa)

    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    time.sleep(1)
    run_cmd(f"sudo ip link set {iface} up")
    run_cmd(f"sudo wpa_supplicant -B -i {iface} -c /tmp/bb_wpa.conf")

    # poll for connection up to TIMEOUT seconds
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if is_connected():
            result[0] = True
            return
        time.sleep(0.5)

    # timed out
    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    result[0] = False

def run(ssid, password=""):
    F         = fonts()
    result    = [None]
    start     = time.time()

    threading.Thread(target=_connect, args=(ssid, password, result),
                     daemon=True).start()

    # spinner + countdown
    while result[0] is None:
        elapsed   = time.time() - start
        remaining = max(0, TIMEOUT - int(elapsed))
        progress  = min(elapsed / TIMEOUT, 1.0)

        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "CONNECTING", ssid[:24], color=C["blue"])

        # spinner
        t    = int(time.time() * 4) % 4
        spin = ["◐", "◓", "◑", "◒"][t]
        sw   = font(44, bold=True).getbbox(spin)[2]
        d.text(((W - sw) // 2, H // 2 - 50),
               spin, font=font(44, bold=True), fill=C["blue"])

        # connecting message
        msg = f'Connecting to "{ssid}"...'
        mw  = F["small"].getbbox(msg)[2]
        d.text(((W - mw) // 2, H // 2 + 10),
               msg, font=F["small"], fill=C["dimwhite"])

        # timeout progress bar
        bar_x, bar_y = 20, H // 2 + 36
        bar_w, bar_h = W - 40, 8
        d.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                    fill=C["dim"], outline=C["dimblue"])
        filled = int(bar_w * progress)
        # bar color shifts red as time runs out
        if remaining > 6:
            bar_col = C["blue"]
        elif remaining > 3:
            bar_col = C["amber"]
        else:
            bar_col = C["red"]
        if filled > 0:
            d.rectangle([bar_x, bar_y, bar_x + filled, bar_y + bar_h],
                        fill=bar_col)

        # countdown
        countdown = f"Timeout in {remaining}s"
        cw        = F["small"].getbbox(countdown)[2]
        d.text(((W - cw) // 2, bar_y + bar_h + 8),
               countdown, font=F["small"], fill=bar_col)

        push(img)
        time.sleep(1 / 30)

    # ── result screen ─────────────────────────────────────────
    if result[0]:
        sync_time()
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "CONNECTED!", ssid[:24], color=C["green"])
        for i, msg in enumerate(["Connected successfully!", "Time synced."]):
            mw = F["body"].getbbox(msg)[2]
            d.text(((W - mw) // 2, H // 2 - 16 + i * 28),
                   msg, font=F["body"], fill=C["green"])
        push(img)
        time.sleep(2)
        return True
    else:
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "FAILED", "could not connect", color=C["red"])
        for i, msg in enumerate([
            "Connection failed.",
            "Please try again.",
        ]):
            mw = F["body"].getbbox(msg)[2]
            d.text(((W - mw) // 2, H // 2 - 20 + i * 28),
                   msg, font=F["body"], fill=C["red"])
        push(img)
        time.sleep(2)
        return False