#!/usr/bin/env python3
"""
BearBox Offline — Saved Networks Screen

No adapter required. Connects directly on wlan0.
Flow:
  - Show saved networks immediately, no hardware checks
  - Tap a network → tear down AP → attempt connect on wlan0
  - Success → return ("connected", ssid) → idle_offline handles the rest
  - Fail    → restore AP → show error → stay on screen
  - Tap outside any button → return ("cycle", None) → go back to clock
"""

import os
import sys
import time
import json
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H
from network.net_utils import check_tap, tapped

CONFIG_PATH  = "/home/bearbox/bearbox/config.json"
MAX_NETWORKS = 4
IFACE        = "wlan0"
AP_IP        = "10.0.0.1"
AP_SSID      = "BearBox-AP"
AP_PASS      = "Bearbox123"

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

# ── Helpers ───────────────────────────────────────────────────

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

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
    except Exception:
        return {}

def _teardown_ap():
    """Bring down the offline AP so wlan0 is free to connect."""
    _run("sudo pkill hostapd 2>/dev/null")
    _run("sudo pkill dnsmasq 2>/dev/null")
    _run(f"sudo ip addr flush dev {IFACE} 2>/dev/null")
    _run(f"nmcli device set {IFACE} managed yes 2>/dev/null")
    time.sleep(0.5)

def _restore_ap():
    """Spin the AP back up after a failed connect attempt."""
    _run(f"nmcli device set {IFACE} managed no 2>/dev/null")
    _run(f"sudo ip link set {IFACE} up")
    _run(f"sudo ip addr add {AP_IP}/24 dev {IFACE} 2>/dev/null")
    with open("/tmp/bb_offline_hostapd.conf", "w") as f:
        f.write(f"interface={IFACE}\ndriver=nl80211\nssid={AP_SSID}\n"
                f"hw_mode=g\nchannel=6\nwmm_enabled=0\nmacaddr_acl=0\n"
                f"auth_algs=1\nignore_broadcast_ssid=0\nwpa=2\n"
                f"wpa_passphrase={AP_PASS}\nwpa_key_mgmt=WPA-PSK\n"
                f"wpa_pairwise=TKIP\nrsn_pairwise=CCMP\n")
    with open("/tmp/bb_offline_dnsmasq.conf", "w") as f:
        f.write(f"interface={IFACE}\n"
                f"dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,24h\n"
                f"dhcp-option=3,{AP_IP}\ndhcp-option=6,8.8.8.8\n")
    _run("sudo hostapd /tmp/bb_offline_hostapd.conf -B 2>/dev/null")
    time.sleep(1)
    _run("sudo dnsmasq --conf-file=/tmp/bb_offline_dnsmasq.conf 2>/dev/null")

def _try_connect(ssid, password):
    """
    Tear down AP, attempt to connect wlan0 to ssid.
    Returns True on success, restores AP on failure.
    """
    _teardown_ap()

    psk_line = f'psk="{password}"' if password else "key_mgmt=NONE"
    wpa = (f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
           f"update_config=1\nnetwork={{\n"
           f"    ssid=\"{ssid}\"\n    {psk_line}\n    priority=10\n}}\n")
    with open("/tmp/bb_saved.conf", "w") as f:
        f.write(wpa)

    _run("sudo pkill wpa_supplicant 2>/dev/null")
    time.sleep(0.5)
    _run(f"sudo ip link set {IFACE} up")
    _run(f"sudo wpa_supplicant -B -i {IFACE} -c /tmp/bb_saved.conf 2>/dev/null")

    # Poll for association (up to 10s)
    deadline = time.time() + 10
    while time.time() < deadline:
        if _run("iwgetid -r 2>/dev/null"):
            break
        time.sleep(0.5)

    # Request DHCP
    _run(f"sudo dhcpcd {IFACE} 2>/dev/null || sudo dhclient {IFACE} 2>/dev/null")

    # Poll for IP + internet (up to 5s)
    deadline2 = time.time() + 5
    while time.time() < deadline2:
        result = _run(f"ip -4 addr show {IFACE}")
        if "inet " in result:
            r = subprocess.run("ping -c 1 -W 2 8.8.8.8",
                               shell=True, capture_output=True)
            if r.returncode == 0:
                return True
        time.sleep(0.5)

    # Failed — restore AP
    _run("sudo pkill wpa_supplicant 2>/dev/null")
    _restore_ap()
    return False

# ── Drawing ───────────────────────────────────────────────────

def _draw_connecting(ssid):
    Fs   = font(13)
    Fbig = font(40, bold=True)
    dots = ["◐", "◓", "◑", "◒"]
    # runs for max 18s to cover _try_connect's full timeout window
    start = time.time()
    while time.time() - start < 18:
        img, d = new_frame(bg=R["bg"])
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(18, 0, 0))
        spin = dots[int(time.time() * 4) % 4]
        sw   = Fbig.getbbox(spin)[2]
        d.text(((W - sw) // 2, H // 2 - 50), spin, font=Fbig, fill=R["red"])
        for i, (txt, col) in enumerate([
            ("Connecting...",  R["dimwhite"]),
            (f'"{ssid}"',      R["white"]),
            (f"via {IFACE}",   R["dimred"]),
        ]):
            tw = Fs.getbbox(txt)[2]
            d.text(((W - tw) // 2, H // 2 + 10 + i * 18), txt, font=Fs, fill=col)
        push(img)
        time.sleep(1 / 15)

def _draw_result(msg, msg2, color):
    F  = font(16, bold=True)
    Fs = font(13)
    img, d = new_frame(bg=R["bg"])
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))
    mw  = F.getbbox(msg)[2]
    mw2 = Fs.getbbox(msg2)[2]
    d.text(((W - mw)  // 2, H // 2 - 20), msg,  font=F,  fill=color)
    d.text(((W - mw2) // 2, H // 2 + 10), msg2, font=Fs, fill=R["dimwhite"])
    push(img)
    time.sleep(2.5)

# ── Main ──────────────────────────────────────────────────────

def run():
    """Returns ("connected", ssid) or ("cycle", None)"""

    F     = font(16, bold=True)
    Ft    = font(20, bold=True)
    Fs    = font(11)
    pulse = 0

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

        img, d = new_frame(bg=R["bg"])
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(18, 0, 0))

        # header
        d.rectangle([0, 0, W, 52], fill=R["panel"])
        d.line([(0, 52), (W, 52)], fill=R["dimred"], width=1)
        title = "SAVED NETWORKS"
        tw    = Ft.getbbox(title)[2]
        d.text(((W - tw) // 2, 8),  title, font=Ft, fill=R["red"])
        sub   = "tap to connect  •  tap outside to go back"
        sw    = Fs.getbbox(sub)[2]
        d.text(((W - sw) // 2, 34), sub,   font=Fs, fill=R["dimred"])

        if not ssids:
            msg  = "No saved networks found"
            msg2 = "SSH in and run: bbsave"
            mw   = F.getbbox(msg)[2]
            mw2  = Fs.getbbox(msg2)[2]
            d.text(((W - mw)  // 2, H // 2 - 14), msg,  font=F,  fill=R["dimred"])
            d.text(((W - mw2) // 2, H // 2 + 14), msg2, font=Fs, fill=R["darkred"])
        else:
            for (bx, by, bw, bh, ssid) in btn_rects:
                amp    = abs((pulse % 60) - 30) / 30.0
                border = (int(50 + amp * 70), 0, 0)
                d.rectangle([bx, by, bx + bw, by + bh],
                            fill=R["panel"], outline=border)
                lw = F.getbbox(ssid[:20])[2]
                lh = F.getbbox(ssid[:20])[3]
                d.text((bx + (bw - lw) // 2, by + (bh - lh) // 2),
                       ssid[:20], font=F, fill=R["white"])
                has_pass = bool(networks.get(ssid, ""))
                tag      = "secured" if has_pass else "open"
                tag_col  = R["dimwhite"] if has_pass else R["midred"]
                tw2      = Fs.getbbox(tag)[2]
                d.text((bx + (bw - tw2) // 2, by + bh - 16),
                       tag, font=Fs, fill=tag_col)

        # footer
        d.rectangle([0, H - 22, W, H], fill=R["panel"])
        hint = f"AP: {AP_SSID}  •  SSH: bearbox@{AP_IP}"
        hw   = Fs.getbbox(hint)[2]
        d.text(((W - hw) // 2, H - 14), hint, font=Fs, fill=R["dimred"])

        push(img)

        if check_tap():
            hit = False
            for (bx, by, bw, bh, ssid) in btn_rects:
                if tapped(bx, by, bw, bh):
                    hit = True
                    _draw_connecting(ssid)
                    if _try_connect(ssid, networks.get(ssid, "")):
                        return "connected", ssid
                    else:
                        _draw_result("Connection failed", f'"{ssid}"', R["red"])
                    break
            if not hit:
                return "cycle", None

        time.sleep(1 / 30)