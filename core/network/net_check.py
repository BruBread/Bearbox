#!/usr/bin/env python3
"""
BearBox Network — Main Entry Point
1. Restore saved time
2. If already connected → sync time → return (silent)
3. Try auto-connect to hotspot via wlan0
4. If connected → sync → CONNECTED screen → return
5. If not → show PLUG IN ADAPTER screen
6. Once adapter detected → AP on wlan0, wlan1 for connecting
7. Launch offline mode
"""

import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from network.net_utils import is_connected, sync_time, run_cmd, get_interface, load_config

TIME_FILE = "/home/bearbox/bearbox/.last_time"

def _restore_time():
    try:
        with open(TIME_FILE) as f:
            last = float(f.read().strip())
        if last > time.time():
            run_cmd(f"sudo date -s '@{int(last)}'")
            print(">> Time restored from file")
        else:
            print(">> Saved time is older than system time, skipping restore")
    except:
        print(">> No saved time file found")

def _try_hotspot():
    cfg      = load_config()
    ssid     = cfg.get("hotspot_ssid", "")
    password = cfg.get("hotspot_password", "")
    if not ssid:
        return False

    print(f">> Trying auto-connect to {ssid}...")
    iface    = get_interface()
    psk_line = ('psk="' + password + '"') if password else "key_mgmt=NONE"
    wpa      = (f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
                f"update_config=1\nnetwork={{\n"
                f"    ssid=\"{ssid}\"\n    {psk_line}\n    priority=10\n}}\n")

    with open("/tmp/bb_auto.conf", "w") as f:
        f.write(wpa)

    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    time.sleep(1)
    run_cmd(f"sudo ip link set {iface} up")
    run_cmd(f"sudo wpa_supplicant -B -i {iface} -c /tmp/bb_auto.conf 2>/dev/null")
    time.sleep(4)
    run_cmd(f"sudo dhcpcd {iface} 2>/dev/null || sudo dhclient {iface} 2>/dev/null")
    time.sleep(2)

    if is_connected():
        print(f">> Auto-connected to {ssid}!")
        return True
    print(f">> Could not connect to {ssid}")
    return False

def run():
    _restore_time()

    # already connected — silent
    if is_connected():
        sync_time()
        return

    # try hotspot auto-connect
    if _try_hotspot():
        sync_time()
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from screen_connected import run as play_connected
        play_connected()
        return

    # no internet — show plug adapter screen first
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from screen_plug_adapter import run as wait_adapter
    wait_adapter()

    # adapter plugged in — launch offline mode
    # wlan0 = AP for SSH access
    # wlan1 = used for connecting to saved networks
    print(">> Launching offline mode with AP...")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../idle"))
    from idle_offline import run as run_offline
    run_offline()

if __name__ == "__main__":
    run()
