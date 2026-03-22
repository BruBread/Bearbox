#!/usr/bin/env python3
"""
BearBox — AP/Siphon Shared Utilities
Sombra-inspired magenta/pink color scheme.
"""

import os
import sys
import time
import subprocess
import select
import struct

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.."))
from display import new_frame, push, draw_scanlines, font, W, H

# ─────────────────────────────────────────────────────────────
# SOMBRA PALETTE
# ─────────────────────────────────────────────────────────────
C = {
    "bg":        (8,   0,   18),
    "panel":     (18,  5,   35),
    "magenta":   (255, 0,   180),
    "pink":      (220, 80,  200),
    "dimpink":   (100, 20,  90),
    "purple":    (140, 0,   200),
    "dimpurple": (40,  0,   60),
    "white":     (240, 220, 255),
    "dimwhite":  (120, 100, 140),
    "dim":       (30,  10,  45),
    "green":     (0,   255, 140),
    "red":       (255, 50,  80),
    "amber":     (255, 180, 0),
    "cyan":      (0,   220, 255),
}

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
    return subprocess.run(cmd, shell=True, capture_output=True,
                          text=True).stdout.strip()

def get_connected_devices():
    devices   = []
    lease_file = "/var/lib/misc/dnsmasq.leases"
    if not os.path.exists(lease_file):
        lease_file = "/tmp/dnsmasq.leases"
    if os.path.exists(lease_file):
        with open(lease_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4:
                    expire          = int(parts[0])
                    mac             = parts[1]
                    ip              = parts[2]
                    host            = parts[3] if parts[3] != "*" else "Unknown"
                    connected_secs  = max(0, 86400 - (expire - int(time.time())))
                    devices.append({
                        "ip":        ip,
                        "mac":       mac,
                        "hostname":  host,
                        "connected": connected_secs,
                    })
    if not devices:
        arp = run_cmd("arp -i wlan0 -n 2>/dev/null")
        for line in arp.split("\n"):
            if "wlan0" in line and "incomplete" not in line and "Address" not in line:
                parts = line.split()
                if len(parts) >= 3:
                    devices.append({
                        "ip":        parts[0],
                        "mac":       parts[2],
                        "hostname":  "Unknown",
                        "connected": 0,
                    })
    return devices

def get_ap_ip():
    ip = run_cmd("ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1")
    return ip or "10.0.0.1"

def kick_device(mac):
    result = run_cmd(f"sudo hostapd_cli -i wlan0 deauthenticate {mac} 2>/dev/null")
    return True

def format_duration(secs):
    if secs < 60:
        return f"{secs}s"
    elif secs < 3600:
        return f"{secs // 60}m"
    else:
        return f"{secs // 3600}h {(secs % 3600) // 60}m"

# ─────────────────────────────────────────────────────────────
# TOUCH
# ─────────────────────────────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 0.8
_touch_fd    = None
_last_tap    = 0
_tap_x       = 0
_tap_y       = 0

def check_tap():
    global _touch_fd, _last_tap, _tap_x, _tap_y
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
                data = _touch_fd.read(16)
                if len(data) == 16:
                    _, _, etype, ecode, evalue = struct.unpack("llHHi", data)
                    if etype == 3 and ecode == 0:
                        _tap_x = int(evalue * W / 4096)
                    if etype == 3 and ecode == 1:
                        _tap_y = int(evalue * H / 4096)
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except:
        _touch_fd = None
    return False

def tapped(x, y, w, h):
    return x <= _tap_x <= x + w and y <= _tap_y <= y + h

# ─────────────────────────────────────────────────────────────
# DRAW HELPERS
# ─────────────────────────────────────────────────────────────

def draw_header(d, F, title, subtitle=None):
    d.rectangle([0, 0, W, 44], fill=C["panel"])
    d.line([(0, 44), (W, 44)], fill=C["magenta"], width=1)
    for pts in [[(6,6),(6,14),(14,14)], [(W-6,6),(W-6,14),(W-14,14)]]:
        d.line([pts[0], pts[1]], fill=C["magenta"], width=1)
        d.line([pts[1], pts[2]], fill=C["magenta"], width=1)
    tw = F["title"].getbbox(title)[2]
    d.text(((W - tw) // 2, 10), title, font=F["title"], fill=C["magenta"])
    if subtitle:
        sw = F["small"].getbbox(subtitle)[2]
        d.text(((W - sw) // 2, 32), subtitle, font=F["small"], fill=C["dimpink"])

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

def draw_scanlines_pink(d):
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(8, 0, 18))
