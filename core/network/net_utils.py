#!/usr/bin/env python3
"""
BearBox Network — Shared Utilities
All shared helpers, fonts, touch, and draw functions.
"""

import os
import sys
import time
import subprocess
import select
import struct

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 0.8

# ─────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────
_F = {}

def fonts():
    if not _F:
        _F["title"] = font(22, bold=True)
        _F["body"]  = font(15)
        _F["small"] = font(11)
        _F["btn"]   = font(16, bold=True)
        _F["big"]   = font(18, bold=True)
        _F["huge"]  = font(32, bold=True)
    return _F

# ─────────────────────────────────────────────────────────────
# SYSTEM
# ─────────────────────────────────────────────────────────────

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def is_connected():
    iface = get_interface()
    result = run_cmd(f"ip -4 addr show {iface} 2>/dev/null")
    if "inet " in result:
        return True
    for iface_name in ["wlan0", "wlan1"]:
        result = run_cmd(f"ip -4 addr show {iface_name} 2>/dev/null")
        if "inet " in result:
            return True
    return False

def has_internet():
    r = subprocess.run("ping -c 1 -W 2 8.8.8.8", shell=True, capture_output=True)
    return r.returncode == 0

def sync_time():
    run_cmd("sudo ntpdate -u pool.ntp.org 2>/dev/null || sudo chronyc makestep 2>/dev/null")

def tplink_connected():
    return "2357:010c" in run_cmd("lsusb") or "TP-Link" in run_cmd("lsusb")

def get_interface():
    ifaces = run_cmd("ls /sys/class/net/")
    if tplink_connected() and "wlan1" in ifaces:
        return "wlan1"
    return "wlan0"

def get_current_ssid():
    return run_cmd("iwgetid -r 2>/dev/null")

def load_config():
    import json
    path = os.path.join(os.path.dirname(__file__), "../../config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def safe_connect(ssid, password=""):
    iface        = get_interface()
    current_ssid = get_current_ssid()
    psk_line     = ('psk="' + password + '"') if password else "key_mgmt=NONE"

    wpa = f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
network={{
    ssid="{ssid}"
    {psk_line}
}}
"""
    with open("/tmp/bb_wpa.conf", "w") as f:
        f.write(wpa)

    if current_ssid != ssid:
        run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
        time.sleep(1)

    run_cmd(f"sudo ip link set {iface} up")
    run_cmd(f"sudo wpa_supplicant -B -i {iface} -c /tmp/bb_wpa.conf")

    deadline = time.time() + 10
    while time.time() < deadline:
        if is_connected():
            return True
        time.sleep(0.5)

    run_cmd("sudo pkill wpa_supplicant 2>/dev/null")
    return False

# ─────────────────────────────────────────────────────────────
# TOUCH
# Linux input_event struct:
#   32-bit kernel:  struct input_event { timeval32 (8B); u16; u16; s32 } = 16 bytes  "iIHHi"
#   64-bit kernel:  struct input_event { timeval64 (16B); u16; u16; s32 } = 24 bytes "llHHi"
# We detect which at first read and stick with it.
# ─────────────────────────────────────────────────────────────

_FMT_64   = "llHHi"
_FMT_32   = "iIHHi"
_SZ_64    = struct.calcsize(_FMT_64)   # 24
_SZ_32    = struct.calcsize(_FMT_32)   # 16

_touch_fd  = None
_last_tap  = 0
_tap_x     = 0
_tap_y     = 0
_evt_size  = _SZ_64   # assume 64-bit until proven otherwise
_evt_fmt   = _FMT_64

def _parse_event(data):
    """Parse one input_event and update _tap_x/_tap_y. Returns True if coords updated."""
    global _tap_x, _tap_y, _evt_size, _evt_fmt
    try:
        _, _, etype, ecode, evalue = struct.unpack(_evt_fmt, data)
        if etype == 3 and ecode == 0:
            _tap_x = int(evalue * W / 4096)
            return True
        if etype == 3 and ecode == 1:
            _tap_y = int(evalue * H / 4096)
            return True
    except struct.error:
        # Wrong size — flip to 32-bit format
        if _evt_fmt == _FMT_64 and len(data) == _SZ_32:
            _evt_fmt  = _FMT_32
            _evt_size = _SZ_32
            try:
                _, _, etype, ecode, evalue = struct.unpack(_evt_fmt, data)
                if etype == 3 and ecode == 0:
                    _tap_x = int(evalue * W / 4096)
                    return True
                if etype == 3 and ecode == 1:
                    _tap_y = int(evalue * H / 4096)
                    return True
            except Exception:
                pass
    return False

def check_tap():
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
                data = _touch_fd.read(_evt_size)
                if len(data) == _evt_size:
                    _parse_event(data)
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except Exception:
        _touch_fd = None
    return False

def tapped(x, y, w, h):
    """Check if the last tap landed inside a rectangle (x, y, w, h)."""
    return x <= _tap_x <= x + w and y <= _tap_y <= y + h

# ─────────────────────────────────────────────────────────────
# DRAW HELPERS
# ─────────────────────────────────────────────────────────────

def draw_header(d, F, title, subtitle=None, color=None):
    color = color or C["amber"]
    d.rectangle([0, 0, W, 44], fill=C["panel"])
    d.line([(0, 44), (W, 44)], fill=color, width=1)
    tw = F["title"].getbbox(title)[2]
    d.text(((W - tw) // 2, 10), title, font=F["title"], fill=color)
    if subtitle:
        sw = F["small"].getbbox(subtitle)[2]
        d.text(((W - sw) // 2, 32), subtitle, font=F["small"], fill=C["dimwhite"])

def draw_btn(d, F, x, y, w, h, label, color, text_color=None):
    text_color = text_color or C["white"]
    d.rectangle([x, y, x+w, y+h], fill=C["panel"], outline=color)
    lw = F["btn"].getbbox(label)[2]
    lh = F["btn"].getbbox(label)[3]
    d.text((x + (w - lw) // 2, y + (h - lh) // 2),
           label, font=F["btn"], fill=text_color)
    return (x, y, w, h)

def draw_two_buttons(d, F, left_label, right_label, left_color, right_color):
    btn_w   = 180
    btn_h   = 52
    btn_y   = H - btn_h - 20
    gap     = 16
    left_x  = (W // 2) - btn_w - gap // 2
    right_x = (W // 2) + gap // 2
    l = draw_btn(d, F, left_x,  btn_y, btn_w, btn_h,
                 left_label,  left_color,  text_color=left_color)
    r = draw_btn(d, F, right_x, btn_y, btn_w, btn_h,
                 right_label, right_color, text_color=right_color)
    return l, r

def wrap_text(text, fnt, max_w):
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if fnt.getbbox(test)[2] <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
