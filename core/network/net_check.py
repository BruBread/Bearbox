#!/usr/bin/env python3
"""
BearBox Network — Main Entry Point

1. Restore saved time  (instant)
2. If already connected → sync time → signal done → return
3. Fire wpa_supplicant for hotspot, then poll every 0.5s instead of
   sleeping 6 fixed seconds.  Signals done_event the moment we know
   the result so the boot animation can exit early.
4. If connected → sync → CONNECTED screen → return
5. If not → launch offline mode
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from network.net_utils import (
    is_connected, has_internet, sync_time,
    run_cmd, get_interface, load_config,
)

TIME_FILE       = "/home/bearbox/bearbox/.last_time"
CONNECT_TIMEOUT = 12    # max seconds to wait for wpa association
POLL_INTERVAL   = 0.5   # how often to check during that window
DHCP_WAIT       = 2.0   # seconds to let dhcpcd settle after association

# ─────────────────────────────────────────────────────────────

def _restore_time():
    try:
        with open(TIME_FILE) as f:
            last = float(f.read().strip())
        if last > time.time():
            run_cmd(f"sudo date -s '@{int(last)}'")
            print(">> Time restored from file")
        else:
            print(">> Saved time older than system clock, skipping")
    except Exception:
        print(">> No saved time file found")

def _try_hotspot(done_event: threading.Event = None):
    """
    Start wpa_supplicant for the configured hotspot and poll until
    we get an IP or time out.  Signals done_event as soon as we know
    either way so the boot animation can exit.
    """
    cfg      = load_config()
    ssid     = cfg.get("hotspot_ssid", "")
    password = cfg.get("hotspot_password", "")
    if not ssid:
        if done_event:
            done_event.set()
        return False

    print(f">> Trying auto-connect to {ssid}...")
    iface    = get_interface()
    psk_line = f'psk="{password}"' if password else "key_mgmt=NONE"
    wpa      = (
        f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
        f"update_config=1\n"
        f"network={{\n"
        f"    ssid=\"{ssid}\"\n"
        f"    {psk_line}\n"
        f"    priority=10\n"
        f"}}\n"
    )
    with open("/tmp/bb_auto.conf", "w") as f:
        f.write(wpa)

    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    time.sleep(0.5)                          # was 1 s — shaved 0.5 s
    run_cmd(f"sudo ip link set {iface} up")
    run_cmd(f"sudo wpa_supplicant -B -i {iface} -c /tmp/bb_auto.conf 2>/dev/null")

    # Poll for association instead of sleeping a fixed 4 s
    deadline = time.time() + CONNECT_TIMEOUT
    associated = False
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        result = run_cmd(f"iwgetid -r 2>/dev/null")
        if result.strip():
            associated = True
            print(f">> Associated with {result.strip()} in {time.time()-deadline+CONNECT_TIMEOUT:.1f}s")
            break

    if not associated:
        print(f">> Could not associate with {ssid}")
        run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
        if done_event:
            done_event.set()
        return False

    # Associated — request DHCP lease
    run_cmd(f"sudo dhcpcd {iface} 2>/dev/null || sudo dhclient {iface} 2>/dev/null")

    # Poll for IP (was a fixed 2 s sleep)
    deadline2 = time.time() + DHCP_WAIT + 2
    while time.time() < deadline2:
        if is_connected():
            print(f">> Auto-connected to {ssid}!")
            if done_event:
                done_event.set()
            return True
        time.sleep(POLL_INTERVAL)

    print(f">> DHCP failed for {ssid}")
    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    if done_event:
        done_event.set()
    return False

# ─────────────────────────────────────────────────────────────

def run(done_event: threading.Event = None):
    """
    Run the full network startup sequence.

    done_event: when provided, it is set() as soon as we know whether
    we're online or offline, so boot_anim can cut the animation short.
    """
    _restore_time()

    # Already have an IP — nothing to do
    if is_connected():
        print(">> Already connected")
        if has_internet():
            sync_time()
        if done_event:
            done_event.set()
        return "connected"

    # Try hotspot auto-connect
    if _try_hotspot(done_event):
        if has_internet():
            sync_time()
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from screen_connected import run as play_connected
        play_connected()
        return "connected"

    # done_event is already set inside _try_hotspot on failure, but
    # guard the no-hotspot-ssid case:
    if done_event and not done_event.is_set():
        done_event.set()

    print(">> No network connection — launching offline mode")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../idle"))
    from idle_offline import run as run_offline
    run_offline()
    return "offline"


if __name__ == "__main__":
    run()
