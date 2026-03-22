#!/usr/bin/env python3
"""
BearBox — Profile Manager
Watches for USB devices and launches the correct profile.

Device → Profile:
  TL-WN722N only          → pentest
  TL-WN722N + ethernet    → ap
  USB Drive               → games
  Rubber Ducky            → rubberducky
  Nothing                 → idle
"""

import subprocess
import os
import sys
import time

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

# ─────────────────────────────────────────────
# DEVICE MAP
# ─────────────────────────────────────────────
PROFILES = {
    "2357:010c": "pentest",       # TL-WN722N
    "03eb:2042": "rubberducky",   # Rubber Ducky
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()

def get_connected_devices():
    output  = run("lsusb")
    devices = []
    for line in output.split("\n"):
        parts = line.split("ID ")
        if len(parts) > 1:
            vid_pid = parts[1].split()[0]
            devices.append(vid_pid)
    return devices

def detect_usb_drive():
    output = run("lsblk -o TRAN,MOUNTPOINT | grep usb")
    return bool(output.strip())

def eth_connected():
    carrier = run("cat /sys/class/net/eth0/carrier 2>/dev/null").strip()
    return carrier == "1"

def get_active_profile():
    devices = get_connected_devices()
    for vid_pid, profile in PROFILES.items():
        if vid_pid in devices:
            if profile == "pentest" and eth_connected():
                return "ap"
            return profile
    if detect_usb_drive():
        return "games"
    return None

def _make_env():
    """Build environment with correct PYTHONPATH."""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{BASE}/core:{BASE}"
    return env

def launch_profile(profile: str):
    profile_map = {
        "pentest":     f"{BASE}/profiles/pentest/ui.py",
        "ap":          f"{BASE}/profiles/wifi/ap/ap_main.py",
        "games":       f"{BASE}/profiles/games/launcher.py",
        "bluetooth":   f"{BASE}/profiles/bluetooth/ui.py",
        "rubberducky": f"{BASE}/profiles/rubberducky/ui.py",
    }

    script = profile_map.get(profile)
    if not script:
        print(f"Unknown profile: {profile}")
        return None
    if not os.path.exists(script):
        print(f"Profile script not found: {script}")
        return None

    print(f"Launching profile: {profile}")
    return subprocess.Popen(
        ["sudo", "-E", "python3", script],
        env=_make_env()
    )

def launch_idle():
    script = f"{BASE}/core/idle/idle_main.py"
    print("Launching idle screen")
    return subprocess.Popen(
        ["sudo", "-E", "python3", script],
        env=_make_env()
    )

def stop_process(process, name):
    if process is None:
        return
    print(f"Stopping: {name}")
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception as e:
        print(f"Error stopping {name}: {e}")

    # show disconnected screen
    from core.screen_disconnect import run as show_disconnect
    show_disconnect()

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def main():
    print("BearBox Profile Manager started")
    current_profile = None
    current_process = None

    while True:
        detected = get_active_profile()

        if detected != current_profile:
            # stop current
            stop_process(current_process, current_profile or "idle")
            current_process = None
            current_profile = detected

            # launch new
            if detected:
                current_process = launch_profile(detected)
            else:
                current_process = launch_idle()

        # check if process died unexpectedly — relaunch if so
        if current_process and current_process.poll() is not None:
            print(f"Process died unexpectedly, relaunching: {current_profile or 'idle'}")
            if current_profile:
                current_process = launch_profile(current_profile)
            else:
                current_process = launch_idle()

        time.sleep(2)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Run as root: sudo python3 profile_manager.py")
        sys.exit(1)
    main()