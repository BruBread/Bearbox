#!/usr/bin/env python3
"""
BearBox Network — Connecting Screen
Shows spinner while connecting. Returns True if successful.
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import (
    fonts, draw_header, run_cmd,
    get_interface, load_config, is_connected, sync_time
)

def _connect(ssid):
    cfg      = load_config()
    password = ""
    if ssid == cfg.get("hotspot_ssid"):
        password = cfg.get("hotspot_password", "")

    iface = get_interface()
    psk_line = ('psk="' + password + '"') if password else "key_mgmt=NONE"
    wpa = f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
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
    time.sleep(3)
    run_cmd(f"sudo dhclient {iface}")
    time.sleep(2)
    return is_connected()

def run(ssid):
    F         = fonts()
    connected = [False]
    done      = [False]

    def _do():
        connected[0] = _connect(ssid)
        done[0]      = True

    threading.Thread(target=_do, daemon=True).start()

    # connecting spinner
    while not done[0]:
        img, d = new_frame()
        draw_scanlines(d)
        draw_header(d, F, "CONNECTING", ssid[:24], color=C["blue"])

        t    = int(time.time() * 4) % 4
        spin = ["◐", "◓", "◑", "◒"][t]
        sw   = font(44, bold=True).getbbox(spin)[2]
        d.text(((W - sw) // 2, H // 2 - 30), spin,
               font=font(44, bold=True), fill=C["blue"])

        msg = f'Connecting to "{ssid}"...'
        mw  = F["small"].getbbox(msg)[2]
        d.text(((W - mw) // 2, H // 2 + 26), msg,
               font=F["small"], fill=C["dimwhite"])

        push(img)
        time.sleep(1 / 15)

    # result screen
    if connected[0]:
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
        msg = "Connection failed. Try again."
        mw  = F["body"].getbbox(msg)[2]
        d.text(((W - mw) // 2, H // 2 - 10), msg,
               font=F["body"], fill=C["red"])
        push(img)
        time.sleep(2)
        return False
