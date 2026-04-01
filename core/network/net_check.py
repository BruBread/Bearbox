#!/usr/bin/env python3
"""
BearBox Network — Main Entry Point

1. Restore saved time
2. If already connected → sync time → signal done → return
3. Try connecting to all saved networks via nmcli (polls, no fixed sleeps)
4. If any connects → sync → CONNECTED screen → return
5. If none connect → launch offline mode

Uses nmcli instead of raw wpa_supplicant so it works alongside
NetworkManager without fighting it.
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from network.net_utils import is_connected, has_internet, sync_time, run_cmd, load_config

TIME_FILE       = "/home/bearbox/bearbox/.last_time"
CONNECT_TIMEOUT = 8     # seconds to wait per network (was 15)
POLL_INTERVAL   = 0.3   # poll more frequently (was 0.5)

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

def _nmcli_connect(ssid, password):
    """
    Connect to a network using nmcli.
    Returns True if connected and has internet.
    """
    print(f">> Trying {ssid}...")

    # Delete any existing connection with this SSID to avoid stale configs
    run_cmd(f"sudo nmcli connection delete \"{ssid}\" 2>/dev/null")

    # Build the connect command
    if password:
        cmd = (f"sudo nmcli device wifi connect \"{ssid}\" "
               f"password \"{password}\" ifname wlan0")
    else:
        cmd = f"sudo nmcli device wifi connect \"{ssid}\" ifname wlan0"

    run_cmd(cmd)

    # Poll for connection
    deadline = time.time() + CONNECT_TIMEOUT
    while time.time() < deadline:
        if is_connected():
            print(f">> Connected to {ssid}!")
            return True
        time.sleep(POLL_INTERVAL)

    print(f">> Failed to connect to {ssid}")
    run_cmd("sudo nmcli device disconnect wlan0 2>/dev/null")
    return False

def _get_all_networks():
    """
    Returns list of (ssid, password) tuples to try.
    Merges hotspot_ssid and saved_networks from config,
    hotspot first.
    """
    cfg      = load_config()
    networks = {}

    # hotspot first
    ssid = cfg.get("hotspot_ssid", "")
    pw   = cfg.get("hotspot_password", "")
    if ssid:
        networks[ssid] = pw

    # then saved networks
    for s, p in cfg.get("saved_networks", {}).items():
        if s not in networks:
            networks[s] = p

    return list(networks.items())

def _try_all_networks(done_event=None):
    """
    Try every saved network in order.
    Returns True as soon as one connects.
    """
    # Scan for available networks first so nmcli knows what's in range
    print(">> Scanning for networks...")
    run_cmd("sudo nmcli device wifi rescan 2>/dev/null")
    time.sleep(0.8)  # was 2 — 0.8s is enough for nmcli to populate results

    # Get available SSIDs
    available = run_cmd("nmcli -t -f SSID device wifi list 2>/dev/null")
    available_ssids = set(line.strip() for line in available.splitlines() if line.strip())
    print(f">> Networks in range: {available_ssids}")

    networks = _get_all_networks()
    if not networks:
        print(">> No saved networks configured")
        if done_event:
            done_event.set()
        return False

    for ssid, password in networks:
        if ssid not in available_ssids:
            print(f">> {ssid} not in range, skipping")
            continue
        if _nmcli_connect(ssid, password):
            if done_event:
                done_event.set()
            return True

    print(">> Could not connect to any saved network")
    if done_event:
        done_event.set()
    return False

# ─────────────────────────────────────────────────────────────

def run(done_event: threading.Event = None):
    """
    Run the full network startup sequence.
    done_event: set as soon as outcome is known so boot_anim can exit early.
    """

    # Force offline flag — set by bboffline, cleared on reboot
    if os.path.exists("/tmp/bb_force_offline"):
        print(">> Force offline flag set — skipping net_check")
        if done_event:
            done_event.set()
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../idle"))
        from idle_offline import run as run_offline
        run_offline()
        return "offline"

    _restore_time()

    # Already connected
    if is_connected():
        print(">> Already connected")
        if has_internet():
            sync_time()
        if done_event:
            done_event.set()
        return "connected"

    # Try all saved networks
    if _try_all_networks(done_event):
        if has_internet():
            sync_time()
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from screen_connected import run as play_connected
        play_connected()
        return "connected"

    if done_event and not done_event.is_set():
        done_event.set()

    print(">> No network — launching offline mode")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../idle"))
    from idle_offline import run as run_offline
    run_offline()
    return "offline"


if __name__ == "__main__":
    run()