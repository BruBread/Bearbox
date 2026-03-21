
"""
BearBox — Profile Manager
Watches for USB devices and loads the correct profile.

Device → Profile mapping:
  TL-WN722N  (2357:010c) → pentest
  USB Drive  (mass storage) → games
  BT Adapter (varies)    → bluetooth
  Rubber Ducky (03eb:2042) → rubberducky
"""

import subprocess
import time
import os
import sys

#Devices
PROFILES = {
    "2357:010c": "pentest",       # TL-WN722N
    "03eb:2042": "rubberducky",   # Rubber Ducky
    # BT adapter — add your ID here when you get one
}

PROFILES_DIR = os.path.join(os.path.dirname(__file__), "../profiles")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()

def get_connected_devices():
    """Return list of vendor:product IDs currently on USB."""
    output = run("lsusb")
    devices = []
    for line in output.split("\n"):
        # format: Bus 001 Device 002: ID 2357:010c TP-Link
        parts = line.split("ID ")
        if len(parts) > 1:
            vid_pid = parts[1].split()[0]
            devices.append(vid_pid)
    return devices

def detect_usb_drive():
    """Return True if a USB mass storage device is mounted."""
    output = run("lsblk -o TRAN,MOUNTPOINT | grep usb")
    return bool(output.strip())

def get_active_profile():
    """Check what's plugged in and return the profile name."""
    devices = get_connected_devices()

    # check known USB IDs first
    for vid_pid, profile in PROFILES.items():
        if vid_pid in devices:
            return profile

    # check for USB drive
    if detect_usb_drive():
        return "games"

    return None

def launch_profile(profile: str):
    """Launch the given profile's main script."""
    profile_map = {
        "pentest":     "profiles/pentest/ui.py",
        "games":       "profiles/games/launcher.py",
        "bluetooth":   "profiles/bluetooth/ui.py",
        "rubberducky": "profiles/rubberducky/ui.py",
    }

    script = profile_map.get(profile)
    if not script:
        print(f"Unknown profile: {profile}")
        return None

    path = os.path.join(os.path.dirname(__file__), "..", script)
    if not os.path.exists(path):
        print(f"Profile script not found: {path}")
        return None

    print(f"Launching profile: {profile}")
    return subprocess.Popen(f"sudo python3 {path}", shell=True)

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
            # kill current profile if running
            if current_process:
                print(f"Stopping profile: {current_profile}")
                current_process.terminate()
                current_process = None

            current_profile = detected

            if detected:
                current_process = launch_profile(detected)
            else:
                print("No device detected — idle")
                # TODO: launch idle screen here

        time.sleep(2)  # poll every 2 seconds

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Run as root: sudo python3 profile_manager.py")
        sys.exit(1)
    main()