#!/usr/bin/env python3
"""
BearBox Idle — Offline Mode
Cycles between red clock and OFFLINE screen on tap.
Silently runs AP in background so you can SSH in and fix connectivity.

AP details:
  SSID:     BearBox-AP
  Password: Bearbox123
  SSH:      bearbox@10.0.0.1
"""

import os
import sys
import time
import select
import threading
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from clock_offline import draw as draw_clock
from hello_offline import draw as draw_offline

# ─────────────────────────────────────────────────────────────
# AP SETUP (silent background)
# ─────────────────────────────────────────────────────────────
AP_IFACE   = "wlan0"
AP_IP      = "10.0.0.1"
AP_SSID    = "BearBox-AP"
AP_PASS    = "Bearbox123"

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def _setup_ap():
    """Silently set up AP so user can SSH in to fix connectivity."""
    try:
        _run(f"nmcli device set {AP_IFACE} managed no 2>/dev/null")
        _run("sudo pkill hostapd 2>/dev/null")
        _run("sudo pkill dnsmasq 2>/dev/null")
        time.sleep(1)

        _run(f"sudo ip link set {AP_IFACE} up")
        _run(f"sudo ip addr flush dev {AP_IFACE}")
        _run(f"sudo ip addr add {AP_IP}/24 dev {AP_IFACE}")

        with open("/tmp/bb_offline_hostapd.conf", "w") as f:
            f.write(f"interface={AP_IFACE}\ndriver=nl80211\nssid={AP_SSID}\n"
                    f"hw_mode=g\nchannel=6\nwmm_enabled=0\nmacaddr_acl=0\n"
                    f"auth_algs=1\nignore_broadcast_ssid=0\nwpa=2\n"
                    f"wpa_passphrase={AP_PASS}\nwpa_key_mgmt=WPA-PSK\n"
                    f"wpa_pairwise=TKIP\nrsn_pairwise=CCMP\n")

        with open("/tmp/bb_offline_dnsmasq.conf", "w") as f:
            f.write(f"interface={AP_IFACE}\n"
                    f"dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,24h\n"
                    f"dhcp-option=3,{AP_IP}\ndhcp-option=6,8.8.8.8\n")

        _run("sudo hostapd /tmp/bb_offline_hostapd.conf -B 2>/dev/null")
        time.sleep(1)
        _run("sudo dnsmasq --conf-file=/tmp/bb_offline_dnsmasq.conf 2>/dev/null")
        print(f">> Offline AP started: {AP_SSID} — SSH: bearbox@{AP_IP}")
    except Exception as e:
        print(f">> AP setup failed: {e}")

def _teardown_ap():
    _run("sudo pkill hostapd 2>/dev/null")
    _run("sudo pkill dnsmasq 2>/dev/null")
    _run(f"sudo ip addr flush dev {AP_IFACE} 2>/dev/null")
    _run(f"nmcli device set {AP_IFACE} managed yes 2>/dev/null")

# ─────────────────────────────────────────────────────────────
# TOUCH
# ─────────────────────────────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 1.2
_touch_fd    = None
_last_tap    = 0

def _check_tap():
    global _touch_fd, _last_tap
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
                _touch_fd.read(16)
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except:
        _touch_fd = None
    return False

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
SCREENS = [
    ("clock",   draw_clock),
    ("offline", draw_offline),
]

def run():
    # start AP silently in background
    threading.Thread(target=_setup_ap, daemon=True).start()

    current = 0
    print("Offline mode — tap to cycle screens")
    print(f"AP: {AP_SSID} | SSH: bearbox@{AP_IP}")

    try:
        while True:
            SCREENS[current][1]()
            if _check_tap():
                current = (current + 1) % len(SCREENS)
                print(f">> Switched to: {SCREENS[current][0]}")
            time.sleep(1/30)
    finally:
        _teardown_ap()

if __name__ == "__main__":
    run()
