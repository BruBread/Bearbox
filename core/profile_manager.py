#!/usr/bin/env python3
"""
BearBox — Profile Manager
Watches for USB devices and launches the correct profile.

Device → Profile:
  TL-WN722N (any)         → pentest  (RECON or SIPHON decided internally)
  USB Drive               → games
  Rubber Ducky            → rubberducky
  USB Keyboard            → keyboard
  Nothing                 → idle

NOTE: TL-WN722N + ethernet used to route to "ap" — that's now handled
inside the pentest profile itself as SIPHON mode. The standalone AP
profile (wlan0 hotspot, no TL-WN722N) is not affected.
"""

import subprocess
import os
import sys
import time

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

PYTHONPATH = f"{BASE}/core:{BASE}:/home/bearbox/.local/lib/python3.13/site-packages"

PROFILES = {
    "2357:010c": "pentest",
    "03eb:2042": "rubberducky",
    "4c4a:4a55": "camera"
}

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
    return bool(run("lsblk -o TRAN,MOUNTPOINT | grep usb").strip())

def eth_connected():
    return run("cat /sys/class/net/eth0/carrier 2>/dev/null").strip() == "1"

def _is_offline_mode():
    r = subprocess.run("pgrep -f idle_offline", shell=True, capture_output=True)
    return r.returncode == 0

def detect_keyboard():
    """
    Returns True if a USB keyboard is connected.
    Checks /proc/bus/input/devices for any USB device with EV_KEY
    that is NOT the touchscreen (event0).
    """
    try:
        with open("/proc/bus/input/devices") as f:
            content = f.read()

        for block in content.split("\n\n"):
            if not block.strip():
                continue
            if "usb" not in block.lower() and "USB" not in block:
                continue
            if "event0" in block:
                continue
            for line in block.split("\n"):
                if line.strip().startswith("B: EV="):
                    try:
                        val = int(line.split("=")[1].strip(), 16)
                        if val & (1 << 1):
                            return True
                    except:
                        pass
    except:
        pass
    return False

def get_active_profile():
    devices = get_connected_devices()

    for vid_pid, profile in PROFILES.items():
        if vid_pid in devices:
            # TL-WN722N always goes to pentest regardless of ethernet or
            # offline mode. RECON vs SIPHON is decided inside pentest/ui.py.
            return profile

    if detect_usb_drive():
        return "games"

    if detect_keyboard():
        return "keyboard"

    return None

def launch_idle():
    script = f"{BASE}/core/idle/idle_main.py"
    print("Launching idle screen")
    return subprocess.Popen(
        ["python3", script],
        env={**os.environ, "PYTHONPATH": PYTHONPATH}
    )

def launch_profile(profile: str):
    profile_map = {
        "pentest":     f"{BASE}/profiles/pentest/ui.py",
        "ap":          f"{BASE}/profiles/wifi/ap/ap_main.py",
        "games":       f"{BASE}/profiles/games/launcher.py",
        "bluetooth":   f"{BASE}/profiles/bluetooth/ui.py",
        "rubberducky": f"{BASE}/profiles/rubberducky/ui.py",
        "keyboard":    f"{BASE}/profiles/keyboard/kb_ui.py",
        "camera":      f"{BASE}/profiles/camera/camera_main.py",
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
        ["python3", script],
        env={**os.environ, "PYTHONPATH": PYTHONPATH}
    )

# Profiles that warrant a "MODULE DISCONNECTED" screen when unplugged.
# idle and keyboard are excluded — no disconnect screen for those.
_DISCONNECT_PROFILES = {"pentest", "ap", "games", "bluetooth", "rubberducky", "camera"}

def stop_process(process, name):
    if process is None:
        return
    was_running = process.poll() is None
    print(f"Stopping: {name}")
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception as e:
        print(f"Error stopping {name}: {e}")

    # Only show disconnect screen when a real hardware-profile was running
    if was_running and name in _DISCONNECT_PROFILES:
        try:
            from core.screen_disconnect import run as show_disconnect
            show_disconnect()
        except Exception as e:
            print(f"Disconnect screen error: {e}")

def main():
    print("BearBox Profile Manager started")
    current_profile = "uninitialized"
    current_process = None

    while True:
        detected = get_active_profile()
        print(f"Detected: {detected}, Current: {current_profile}")

        if detected != current_profile:
            stop_process(current_process, current_profile or "idle")
            current_process = None
            current_profile = detected
            if detected:
                current_process = launch_profile(detected)
            else:
                print("About to launch idle...")
                current_process = launch_idle()
                print(f"Idle PID: {current_process.pid if current_process else 'NONE'}")

        if current_process and current_process.poll() is not None:
            print(f"Process died, relaunching: {current_profile or 'idle'}")
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