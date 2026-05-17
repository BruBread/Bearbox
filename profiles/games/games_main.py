"""
profiles/games/games_main.py
Entry point for the BearBox games profile (USB drive trigger → Doom).

Sequence:
  1. Stop bearbox.service and wait for full teardown.
  2. Show scrolling green terminal boot animation (games_display).
  3. Scan /proc/bus/input/devices for a keyboard (EV_KEY bitmask).
     If missing, show RED "CONNECT KEYBOARD" screen and poll.
  4. Play TV-ON animation (games_display).
  5. exec() doomgeneric — hands off completely, no return.
"""

import os
import sys
import subprocess
import time

# ── Path setup ────────────────────────────────────────────────────────────────
_PROFILE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT        = os.path.join(_PROFILE_DIR, "..", "..")
sys.path.insert(0, _ROOT)

from profiles.games.games_display import (
    terminal_boot_sequence,
    keyboard_wait_screen,
    tv_on_animation,
)

# ── Doom binary + WAD ─────────────────────────────────────────────────────────
DOOM_BIN = "/home/bearbox/doomgeneric/doomgeneric/doomgeneric"
DOOM_WAD = "/home/bearbox/freedoom-0.13.0/freedoom1.wad"
DOOM_CMD = ["sudo", DOOM_BIN, "-iwad", DOOM_WAD]

# ── Keyboard detection ────────────────────────────────────────────────────────
# EV_KEY bitmask flag: bit 1 set in the EV= hex field.
# /proc/bus/input/devices lists all input nodes; same method as profile_manager.
_EVKEY_BIT = 0x2   # EV_KEY is event type 1 → bit 1

def _has_keyboard() -> bool:
    """
    Return True if at least one keyboard (EV_KEY capable) input device exists.
    Reads /proc/bus/input/devices; never opens /dev/input/event* directly.
    """
    try:
        with open("/proc/bus/input/devices", "r") as f:
            content = f.read()
    except OSError:
        return False

    current_ev = None
    has_event  = False

    for line in content.splitlines():
        line = line.strip()

        if line.startswith("B: EV="):
            try:
                current_ev = int(line.split("=", 1)[1], 16)
            except ValueError:
                current_ev = None

        elif line.startswith("H: Handlers="):
            handlers   = line.split("=", 1)[1]
            has_event  = any(
                tok.startswith("event") for tok in handlers.split()
            )

        elif line == "":
            # end of a device block — evaluate it
            if current_ev is not None and has_event:
                if current_ev & _EVKEY_BIT:
                    return True
            current_ev = None
            has_event  = False

    # catch last block if file doesn't end with blank line
    if current_ev is not None and has_event:
        if current_ev & _EVKEY_BIT:
            return True

    return False


# ── Step 1: stop bearbox.service ──────────────────────────────────────────────
def _stop_service():
    """
    Run `systemctl stop bearbox` and block until it exits.
    Uses check=False — if the service is already stopped that's fine.
    Times out after 10 s to avoid hanging forever.
    """
    subprocess.run(
        ["systemctl", "stop", "bearbox"],
        timeout=10,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Brief settle — give any display processes time to release /dev/fb*
    time.sleep(0.3)


# ── Step 5: exec Doom ─────────────────────────────────────────────────────────
def _launch_doom():
    """
    Replace this process with doomgeneric.
    os.execvp is preferred so Doom inherits our environment cleanly.
    Falls back to subprocess.run if execvp raises (e.g. running as non-root
    and sudo needs a password — shouldn't happen on BearBox, but be safe).
    """
    try:
        os.execvp(DOOM_CMD[0], DOOM_CMD)
    except OSError as exc:
        # Last-resort fallback — shouldn't normally be reached
        sys.stderr.write(f"[games_main] execvp failed: {exc}, trying subprocess\n")
        subprocess.run(DOOM_CMD, check=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # 1. Stop the bearbox service
    _stop_service()

    # 2. Scrolling green boot terminal
    terminal_boot_sequence()

    # 3. Keyboard check — show waiting screen until found
    if not _has_keyboard():
        while not _has_keyboard():
            keyboard_wait_screen(pulse=True)
            time.sleep(0.25)   # poll interval

        # Keyboard just appeared — one brief "found" flash before continuing
        from core.display import new_frame, push, font, W, H
        _f = font(size=18, bold=True)
        img, d = new_frame()
        img.paste((0, 10, 0), [0, 0, W, H])
        d.text((W // 2, H // 2), "KEYBOARD DETECTED",
               font=_f, fill=(0, 255, 70), anchor="mm")
        push(img)
        time.sleep(0.6)

    # 4. TV-on animation
    tv_on_animation()

    # 5. Hand off to Doom — no return
    _launch_doom()


if __name__ == "__main__":
    main()
