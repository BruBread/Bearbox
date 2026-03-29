#!/usr/bin/env python3
"""
BearBox Idle — Offline Mode
Boots straight into red clock with AP running in background.
3 screens cycling on tap:
  0. Red Clock
  1. OFFLINE screen
  2. Saved Networks (shows adapter screen if needed before connecting)

AP on wlan0 starts immediately — no adapter required for clock/offline screens.
Adapter only needed when user tries to connect via saved networks screen.

Loop order (fixed):
  1. Draw current screen
  2. Check tap → increment current
  3. If NEW current is 2, networks screen runs on next iteration
  4. Check internet periodically
  This ensures every screen actually renders before we act on it.
"""

import os
import sys
import time
import select
import struct
import threading
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from clock_offline    import draw as draw_clock
from hello_offline    import draw as draw_offline
from networks_offline import run  as run_networks

AP_IFACE = "wlan0"
AP_IP    = "10.0.0.1"
AP_SSID  = "BearBox-AP"
AP_PASS  = "Bearbox123"

SCREEN_NAMES = ["clock", "offline", "networks"]
CHECK_EVERY  = 10

# ── AP ────────────────────────────────────────────────────────

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def _is_connected():
    result = subprocess.run(
        "ip -4 addr show wlan0", shell=True, capture_output=True, text=True
    ).stdout
    for line in result.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            ip = line.split()[1].split("/")[0]
            if ip != AP_IP and not ip.startswith("169.254"):
                return True
    return False

def _setup_ap():
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
        print(f">> Offline AP: {AP_SSID} | SSH: bearbox@{AP_IP}")
    except Exception as e:
        print(f">> AP setup failed: {e}")

def _teardown_ap():
    _run("sudo pkill hostapd 2>/dev/null")
    _run("sudo pkill dnsmasq 2>/dev/null")
    _run(f"sudo ip addr flush dev {AP_IFACE} 2>/dev/null")
    _run(f"nmcli device set {AP_IFACE} managed yes 2>/dev/null")

# ── Touch — 64/32-bit safe ────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 1.2

_FMT_64  = "llHHi"
_FMT_32  = "iIHHi"
_SZ_64   = struct.calcsize(_FMT_64)
_SZ_32   = struct.calcsize(_FMT_32)

_touch_fd = None
_last_tap = 0
_evt_size = _SZ_64
_evt_fmt  = _FMT_64

def _check_tap():
    global _touch_fd, _last_tap, _evt_size, _evt_fmt
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
                data = _touch_fd.read(_evt_size)
                if not data:
                    break
                if len(data) == _SZ_32 and _evt_fmt == _FMT_64:
                    _evt_fmt  = _FMT_32
                    _evt_size = _SZ_32
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except Exception:
        _touch_fd = None
    return False

# ── Main loop ─────────────────────────────────────────────────

def run():
    threading.Thread(target=_setup_ap, daemon=True).start()

    current   = 0
    last_inet = time.time()

    print(f"Offline mode | AP: {AP_SSID} | SSH: bearbox@{AP_IP}")

    try:
        while True:

            # ── 1. Draw current screen ────────────────────────
            if current == 0:
                draw_clock()
            elif current == 1:
                draw_offline()
            elif current == 2:
                # Networks screen blocks internally until user connects or backs out
                result, ssid = run_networks()
                if result == "connected":
                    print(f">> Connected to {ssid}!")
                    _teardown_ap()
                    from screen_connected import run as play_connected
                    play_connected()
                    subprocess.run("sudo systemctl restart bearbox", shell=True)
                    return
                else:
                    # user backed out — go back to clock
                    current = 0
                    continue

            # ── 2. Check tap → update current for next frame ──
            if _check_tap():
                current = (current + 1) % 3
                print(f">> Screen: {SCREEN_NAMES[current]}")

            # ── 3. Periodic internet check ────────────────────
            if time.time() - last_inet > CHECK_EVERY:
                last_inet = time.time()
                if _is_connected():
                    print(">> Network detected!")
                    _teardown_ap()
                    from screen_connected import run as play_connected
                    play_connected()
                    try:
                        from network.net_utils import has_internet, sync_time
                        if has_internet():
                            sync_time()
                    except Exception:
                        pass
                    os.execv(
                        sys.executable,
                        [sys.executable,
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "idle_main.py")]
                    )
                    return  # never reached

            time.sleep(1 / 30)

    finally:
        _teardown_ap()


if __name__ == "__main__":
    run()