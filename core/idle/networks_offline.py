#!/usr/bin/env python3
"""
BearBox Offline — Saved Networks Screen
Shows adapter screen first if TL-WN722N not plugged in.
Uses wlan1 for connecting while wlan0 stays as AP.
Returns ("connected", ssid), ("cycle", None)
"""

import os
import sys
import time
import json
import select
import subprocess
import struct

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H

CONFIG_PATH   = "/home/bearbox/bearbox/config.json"
MAX_NETWORKS  = 4
CONNECT_IFACE = "wlan1"

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

TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 0.8
_touch_fd    = None
_last_tap    = 0
_tap_x       = 0
_tap_y       = 0

def _check_tap():
    global _touch_fd, _last_tap, _tap_x, _tap_y
    if not os.path.exists(TOUCH_DEV):
        return False
    try:
        if _touch_fd is None:
            _touch_fd = open(TOUCH_DEV, "rb")
        r, _, _ = select.select([_touch_fd], [], [], 0)
        if r:
            while True:
                r2, _, _ = select.select([_touch_fd], [], [], 0)
                if not r2:
                    break
                data = _touch_fd.read(16)
                if len(data) == 16:
                    _, _, etype, ecode, evalue = struct.unpack("llHHi", data)
                    if etype == 3 and ecode == 0:
                        _tap_x = int(evalue * W / 4096)
                    if etype == 3 and ecode == 1:
                        _tap_y = int(evalue * H / 4096)
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except:
        _touch_fd = None
    return False

def _tapped(x, y, w, h):
    return x <= _tap_x <= x + w and y <= _tap_y <= y + h

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def _tplink_connected():
    out = subprocess.run("lsusb", shell=True, capture_output=True, text=True).stdout
    return "2357:010c" in out or "TP-Link" in out

def _load_saved_networks():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        networks     = cfg.get("saved_networks", {})
        hotspot_ssid = cfg.get("hotspot_ssid", "")
        hotspot_pass = cfg.get("hotspot_password", "")
        if hotspot_ssid and hotspot_ssid not in networks:
            networks[hotspot_ssid] = hotspot_pass
        return networks
    except:
        return {}

def _try_connect(ssid, password):
    iface    = CONNECT_IFACE
    psk_line = ('psk="' + password + '"') if password else "key_mgmt=NONE"
    wpa      = (f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
                f"update_config=1\nnetwork={{\n"
                f"    ssid=\"{ssid}\"\n    {psk_line}\n    priority=10\n}}\n")
    with open("/tmp/bb_saved.conf", "w") as f:
        f.write(wpa)
    _run(f"sudo pkill -f 'wpa_supplicant.*{iface}' 2>/dev/null")
    time.sleep(0.5)
    _run(f"sudo ip link set {iface} up")
    _run(f"sudo wpa_supplicant -B -i {iface} -c /tmp/bb_saved.conf 2>/dev/null")
    time.sleep(4)
    _run(f"sudo dhcpcd {iface} 2>/dev/null || sudo dhclient {iface} 2>/dev/null")
    time.sleep(2)
    r = subprocess.run("ping -c 1 -W 2 8.8.8.8", shell=True, capture_output=True)
    return r.returncode == 0

def _draw_connecting(ssid):
    Fs    = font(13)
    start = time.time()
    while time.time() - start < 8:
        img, d = new_frame(bg=R["bg"])
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(18, 0, 0))
        t    = int(time.time() * 4) % 4
        spin = ["◐", "◓", "◑", "◒"][t]
        sw   = font(40, bold=True).getbbox(spin)[2]
        d.text(((W-sw)//2, H//2-40), spin, font=font(40, bold=True), fill=R["red"])
        msg  = f'Connecting via {CONNECT_IFACE}...'
        msg2 = f'"{ssid}"'
        mw   = Fs.getbbox(msg)[2]
        mw2  = Fs.getbbox(msg2)[2]
        d.text(((W-mw)//2,  H//2+10), msg,  font=Fs, fill=R["dimwhite"])
        d.text(((W-mw2)//2, H//2+28), msg2, font=Fs, fill=R["white"])
        push(img)
        time.sleep(1/15)

def run():
    """Returns ("connected", ssid) or ("cycle", None)"""

    # check adapter — show adapter screen if needed
    if not _tplink_connected():
        from screen_plug_adapter import run as wait_adapter
        result = wait_adapter()
        if result == "connected":
            return "connected", "auto"   # internet came back while waiting
        if result == "back" or not _tplink_connected():
            return "cycle", None

    F      = font(16, bold=True)
    Ft     = font(20, bold=True)
    Fs     = font(11)
    pulse  = 0

    networks = _load_saved_networks()
    ssids    = list(networks.keys())[:MAX_NETWORKS]

    BTN_W  = 210
    BTN_H  = 60
    GAP    = 10
    grid_w = BTN_W * 2 + GAP
    grid_x = (W - grid_w) // 2
    grid_y = 62

    btn_rects = []
    for i, ssid in enumerate(ssids):
        col = i % 2
        row = i // 2
        bx  = grid_x + col * (BTN_W + GAP)
        by  = grid_y + row * (BTN_H + GAP)
        btn_rects.append((bx, by, BTN_W, BTN_H, ssid))

    while True:
        pulse += 1

        # adapter unplugged while on this screen — go back
        if not _tplink_connected():
            return "cycle", None

        img, d = new_frame(bg=R["bg"])
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(18, 0, 0))

        # header
        d.rectangle([0, 0, W, 52], fill=R["panel"])
        d.line([(0, 52), (W, 52)], fill=R["dimred"], width=1)
        title = "SAVED NETWORKS"
        tw    = Ft.getbbox(title)[2]
        d.text(((W-tw)//2, 8), title, font=Ft, fill=R["red"])
        sub   = "tap to connect  •  tap outside to go back"
        sw    = Fs.getbbox(sub)[2]
        d.text(((W-sw)//2, 36), sub, font=Fs, fill=R["dimred"])

        if not ssids:
            msg  = "No saved networks found"
            msg2 = "SSH in: bbconnect"
            mw   = F.getbbox(msg)[2]
            mw2  = Fs.getbbox(msg2)[2]
            d.text(((W-mw)//2,  H//2-14), msg,  font=F,  fill=R["dimred"])
            d.text(((W-mw2)//2, H//2+14), msg2, font=Fs, fill=R["darkred"])
        else:
            for (bx, by, bw, bh, ssid) in btn_rects:
                amp    = abs((pulse % 60) - 30) / 30.0
                border = (int(50 + amp * 70), 0, 0)
                d.rectangle([bx, by, bx+bw, by+bh],
                            fill=R["panel"], outline=border)
                lw = F.getbbox(ssid[:20])[2]
                lh = F.getbbox(ssid[:20])[3]
                d.text((bx+(bw-lw)//2, by+(bh-lh)//2),
                       ssid[:20], font=F, fill=R["white"])
                has_pass = bool(networks.get(ssid, ""))
                tag      = "secured" if has_pass else "open"
                tag_col  = R["dimwhite"] if has_pass else R["midred"]
                tw2      = Fs.getbbox(tag)[2]
                d.text((bx+(bw-tw2)//2, by+bh-16), tag, font=Fs, fill=tag_col)

        # footer
        d.rectangle([0, H-22, W, H], fill=R["panel"])
        hint = "AP: BearBox-AP  •  SSH: bearbox@10.0.0.1"
        hw   = Fs.getbbox(hint)[2]
        d.text(((W-hw)//2, H-14), hint, font=Fs, fill=R["dimred"])

        push(img)

        if _check_tap():
            hit = False
            for (bx, by, bw, bh, ssid) in btn_rects:
                if _tapped(bx, by, bw, bh):
                    hit = True
                    _draw_connecting(ssid)
                    if _try_connect(ssid, networks.get(ssid, "")):
                        return "connected", ssid
                    else:
                        img2, d2 = new_frame(bg=R["bg"])
                        for y in range(0, H, 4):
                            d2.line([(0, y), (W, y)], fill=(18, 0, 0))
                        msg  = "Connection failed"
                        msg2 = f'"{ssid}"'
                        mw   = F.getbbox(msg)[2]
                        mw2  = F.getbbox(msg2)[2]
                        d2.text(((W-mw)//2,  H//2-20), msg,  font=F, fill=R["red"])
                        d2.text(((W-mw2)//2, H//2+10), msg2, font=F, fill=R["dimwhite"])
                        push(img2)
                        time.sleep(2)
                    break
            if not hit:
                return "cycle", None

        time.sleep(1/30)
