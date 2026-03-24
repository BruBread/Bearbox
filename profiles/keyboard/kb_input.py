#!/usr/bin/env python3
"""
BearBox Keyboard — Input Handler
Reads raw keyboard events from /dev/input/event* devices.
Handles key repeat, shift, caps lock, special keys.
No extra drivers needed — standard Linux HID input.
"""

import os
import select
import struct
import threading

# Linux input event format: timeval (8 bytes) + type (2) + code (2) + value (4) = 16 bytes
# On 64-bit: timeval is two longs = 16 bytes, so total = 24 bytes
# We try both and pick whichever parses cleanly.
EVENT_FORMAT_64 = "llHHi"   # 24 bytes — 64-bit Pi OS
EVENT_FORMAT_32 = "iIHHi"   # 16 bytes — 32-bit (fallback)
EVENT_SIZE_64   = struct.calcsize(EVENT_FORMAT_64)
EVENT_SIZE_32   = struct.calcsize(EVENT_FORMAT_32)

EV_KEY   = 1
KEY_PRESS   = 1
KEY_REPEAT  = 2
KEY_RELEASE = 0

# ── Keycode → character map ───────────────────────────────────
# (unshifted, shifted)
KEYMAP = {
    2:  ("1", "!"),   3:  ("2", "@"),   4:  ("3", "#"),
    5:  ("4", "$"),   6:  ("5", "%"),   7:  ("6", "^"),
    8:  ("7", "&"),   9:  ("8", "*"),   10: ("9", "("),
    11: ("0", ")"),   12: ("-", "_"),   13: ("=", "+"),
    16: ("q", "Q"),   17: ("w", "W"),   18: ("e", "E"),
    19: ("r", "R"),   20: ("t", "T"),   21: ("y", "Y"),
    22: ("u", "U"),   23: ("i", "I"),   24: ("o", "O"),
    25: ("p", "P"),   26: ("[", "{"),   27: ("]", "}"),
    30: ("a", "A"),   31: ("s", "S"),   32: ("d", "D"),
    33: ("f", "F"),   34: ("g", "G"),   35: ("h", "H"),
    36: ("j", "J"),   37: ("k", "K"),   38: ("l", "L"),
    39: (";", ":"),   40: ("'", '"'),   41: ("`", "~"),
    43: ("\\", "|"),
    44: ("z", "Z"),   45: ("x", "X"),   46: ("c", "C"),
    47: ("v", "V"),   48: ("b", "B"),   49: ("n", "N"),
    50: ("m", "M"),   51: (",", "<"),   52: (".", ">"),
    53: ("/", "?"),
    57: (" ", " "),   # space
}

# Special keycodes
KEY_BACKSPACE = 14
KEY_ENTER     = 28
KEY_TAB       = 15
KEY_ESC       = 1
KEY_UP        = 103
KEY_DOWN      = 108
KEY_LEFT      = 105
KEY_RIGHT     = 106
KEY_LSHIFT    = 42
KEY_RSHIFT    = 54
KEY_LCTRL     = 29
KEY_RCTRL     = 97
KEY_CAPSLOCK  = 58
KEY_HOME      = 102
KEY_END       = 107
KEY_PGUP      = 104
KEY_PGDN      = 109
KEY_DELETE    = 111
KEY_INSERT    = 110

SHIFT_KEYS   = {KEY_LSHIFT, KEY_RSHIFT}
CTRL_KEYS    = {KEY_LCTRL, KEY_RCTRL}
MODIFIER_KEYS = SHIFT_KEYS | CTRL_KEYS | {KEY_CAPSLOCK}


def find_keyboard_device():
    """Find the first keyboard-like event device."""
    input_dir = "/dev/input"
    by_id     = "/dev/input/by-id"

    # prefer by-id symlinks with 'kbd' in name
    if os.path.exists(by_id):
        for name in os.listdir(by_id):
            if "kbd" in name.lower() or "keyboard" in name.lower():
                path = os.path.join(by_id, name)
                real = os.path.realpath(path)
                if os.path.exists(real):
                    return real

    # fall back: scan /dev/input/event* and pick one that has key events
    # skip event0 which is usually the touchscreen
    for i in range(1, 20):
        path = f"{input_dir}/event{i}"
        if not os.path.exists(path):
            continue
        try:
            # check /proc/bus/input/devices for keyboard capability
            with open("/proc/bus/input/devices") as f:
                content = f.read()
            # find the block for this event number
            for block in content.split("\n\n"):
                if f"event{i}" in block and (
                    "keyboard" in block.lower() or
                    "kbd" in block.lower() or
                    # check EV= bitmask: 0x120013 or similar includes EV_KEY
                    ("EV=" in block and _has_ev_key(block))
                ):
                    return path
        except:
            pass

    # last resort: event1
    if os.path.exists(f"{input_dir}/event1"):
        return f"{input_dir}/event1"

    return None


def _has_ev_key(block):
    """Check if the EV= bitmask in a /proc/bus/input/devices block includes EV_KEY (bit 1)."""
    try:
        for line in block.split("\n"):
            if line.strip().startswith("B: EV="):
                val = int(line.split("=")[1].strip(), 16)
                return bool(val & (1 << 1))
    except:
        pass
    return False


class KeyboardReader:
    """
    Threaded keyboard reader.
    Call .get_char() from main loop — returns a char string or special key name,
    or None if nothing pending.

    Special key names returned as strings:
        "BACKSPACE", "ENTER", "TAB", "ESC",
        "UP", "DOWN", "LEFT", "RIGHT",
        "HOME", "END", "PGUP", "PGDN", "DELETE"
        "CTRL_C", "CTRL_D", "CTRL_L", "CTRL_U", "CTRL_W", "CTRL_A", "CTRL_E"
    """

    def __init__(self, device_path=None):
        self.device   = device_path or find_keyboard_device()
        self._fd      = None
        self._fmt     = EVENT_FORMAT_64
        self._evsz    = EVENT_SIZE_64
        self._shift   = False
        self._ctrl    = False
        self._caps    = False
        self._queue   = []
        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None

    def start(self):
        if not self.device:
            print("[keyboard] No keyboard device found")
            return False
        try:
            self._fd = open(self.device, "rb")
            # detect struct size from first read
            self._running = True
            self._thread  = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True
        except PermissionError:
            print(f"[keyboard] Permission denied: {self.device} — run as root")
            return False
        except Exception as e:
            print(f"[keyboard] Failed to open {self.device}: {e}")
            return False

    def stop(self):
        self._running = False
        if self._fd:
            try:
                self._fd.close()
            except:
                pass

    def get_char(self):
        """Returns next pending key string, or None."""
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
        return None

    def _read_loop(self):
        # auto-detect struct size on first successful parse
        detected = False
        while self._running:
            try:
                r, _, _ = select.select([self._fd], [], [], 0.1)
                if not r:
                    continue
                data = self._fd.read(self._evsz)
                if not data or len(data) != self._evsz:
                    # try the other size
                    if not detected:
                        self._fmt  = EVENT_FORMAT_32
                        self._evsz = EVENT_SIZE_32
                    continue
                self._parse(data)
                detected = True
            except Exception as e:
                if self._running:
                    print(f"[keyboard] Read error: {e}")
                break

    def _parse(self, data):
        try:
            unpacked = struct.unpack(self._fmt, data)
            etype    = unpacked[-3]
            ecode    = unpacked[-2]
            evalue   = unpacked[-1]
        except:
            return

        if etype != EV_KEY:
            return

        if evalue == KEY_RELEASE:
            if ecode in SHIFT_KEYS:
                self._shift = False
            elif ecode in CTRL_KEYS:
                self._ctrl = False
            return

        if evalue not in (KEY_PRESS, KEY_REPEAT):
            return

        # modifiers
        if ecode in SHIFT_KEYS:
            self._shift = True
            return
        if ecode in CTRL_KEYS:
            self._ctrl = True
            return
        if ecode == KEY_CAPSLOCK and evalue == KEY_PRESS:
            self._caps = not self._caps
            return

        key = self._translate(ecode)
        if key:
            with self._lock:
                self._queue.append(key)

    def _translate(self, ecode):
        # ctrl combos
        if self._ctrl:
            ctrl_map = {
                30: "CTRL_A",  # a
                32: "CTRL_D",  # d — EOF
                33: "CTRL_F",
                35: "CTRL_H",
                38: "CTRL_L",  # clear
                49: "CTRL_N",
                25: "CTRL_P",
                20: "CTRL_T",
                22: "CTRL_U",  # clear line
                47: "CTRL_V",
                23: "CTRL_W",  # delete word
                45: "CTRL_X",
                21: "CTRL_Y",
                44: "CTRL_Z",
                46: "CTRL_C",  # interrupt
                3:  "CTRL_C",  # keycode 3 also maps to ^C on some boards
                28: "CTRL_M",  # enter
                14: "CTRL_H",  # backspace
                19: "CTRL_R",  # history search
                35: "CTRL_H",
                36: "CTRL_J",
                37: "CTRL_K",
                4:  "CTRL_C",
            }
            return ctrl_map.get(ecode)

        # special keys
        special = {
            KEY_BACKSPACE: "BACKSPACE",
            KEY_ENTER:     "ENTER",
            KEY_TAB:       "TAB",
            KEY_ESC:       "ESC",
            KEY_UP:        "UP",
            KEY_DOWN:      "DOWN",
            KEY_LEFT:      "LEFT",
            KEY_RIGHT:     "RIGHT",
            KEY_HOME:      "HOME",
            KEY_END:       "END",
            KEY_PGUP:      "PGUP",
            KEY_PGDN:      "PGDN",
            KEY_DELETE:    "DELETE",
        }
        if ecode in special:
            return special[ecode]

        # printable characters
        if ecode in KEYMAP:
            unshifted, shifted = KEYMAP[ecode]
            # caps lock only affects letters
            is_letter = unshifted.isalpha()
            use_shift = self._shift
            if is_letter and self._caps:
                use_shift = not use_shift
            return shifted if use_shift else unshifted

        return None
