#!/usr/bin/env python3
"""
BearBox — Plug In Adapter Screen (Offline)
Waits for TL-WN722N to be plugged in.
Tap anywhere to go back.
Also watches for internet coming back.
Returns: "detected", "back", or "connected"
"""

import os
import sys
import time
import random
import string
import select
import struct
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H

R = {
    "bg":       (12,  0,   0),
    "panel":    (22,  0,   0),
    "red":      (255, 40,  40),
    "midred":   (180, 20,  20),
    "dimred":   (70,  0,   0),
    "darkred":  (25,  0,   0),
    "white":    (255, 220, 220),
    "dimwhite": (140, 80,  80),
}

_BG_CHARS = list(string.ascii_letters + string.digits + "!@#$%^&*<>/?\\|[]{}=+-")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()
    def _reset(self):
        self.speed = random.uniform(1.5, 4.0)
        self.chars = [{"char": random.choice(_BG_CHARS),
                       "y":    random.randint(-H, 0) - i * 12}
                      for i in range(random.randint(4, 10))]
    def update(self):
        for c in self.chars:
            c["y"] += self.speed
            if random.random() < 0.05:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in self.chars):
            self._reset()
    def draw(self, d, fnt):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                idx  = self.chars.index(c)
                frac = 1 - (idx / max(len(self.chars)-1, 1))
                b    = int(frac * 45)
                d.text((self.x, y), c["char"], font=fnt, fill=(b, 0, 0))

def _tplink_connected():
    out = subprocess.run("lsusb", shell=True, capture_output=True, text=True).stdout
    return "2357:010c" in out or "TP-Link" in out

def _is_connected():
    r = subprocess.run("ping -c 1 -W 1 8.8.8.8", shell=True, capture_output=True)
    return r.returncode == 0

TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 0.8

_FMT_64   = "llHHi"
_FMT_32   = "iIHHi"
_SZ_64    = struct.calcsize(_FMT_64)
_SZ_32    = struct.calcsize(_FMT_32)

_touch_fd  = None
_last_tap  = 0
_evt_size  = _SZ_64
_evt_fmt   = _FMT_64

def _check_tap():
    global _touch_fd, _last_tap, _evt_size, _evt_fmt
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
                if not data:
                    break
                if len(data) == _SZ_32 and _evt_fmt == _FMT_64:
                    _evt_fmt  = _FMT_32
                    _evt_size = _SZ_32
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except Exception:
        _touch_fd = None
    return False

def run():
    """Returns 'detected', 'back', or 'connected'"""
    if _tplink_connected():
        return "detected"

    F      = font(22, bold=True)
    Fb     = font(16, bold=True)
    Fs     = font(12)
    Fbg    = font(10)
    cols   = [_BgCol(int((i+0.5)*W/16)) for i in range(16)]
    pulse  = 0
    last_inet_check = time.time()

    while True:
        pulse += 1

        # check internet every 5 seconds
        if time.time() - last_inet_check > 5:
            last_inet_check = time.time()
            if _is_connected():
                return "connected"

        # adapter plugged in
        if _tplink_connected():
            img, d = new_frame(bg=R["bg"])
            for y in range(0, H, 4):
                d.line([(0, y), (W, y)], fill=(18, 0, 0))
            F2   = font(20, bold=True)
            msg  = "ADAPTER DETECTED"
            msg2 = "starting up..."
            mw   = F2.getbbox(msg)[2]
            mw2  = Fs.getbbox(msg2)[2]
            d.text(((W-mw)//2,  H//2-20), msg,  font=F2, fill=R["red"])
            d.text(((W-mw2)//2, H//2+14), msg2, font=Fs, fill=R["dimwhite"])
            push(img)
            time.sleep(1.5)
            return "detected"

        # tap to go back
        if _check_tap():
            return "back"

        img, d = new_frame(bg=R["bg"])

        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(18, 0, 0))

        for col in cols:
            col.update()
            col.draw(d, Fbg)

        # header
        d.rectangle([0, 0, W, 48], fill=R["panel"])
        d.line([(0, 48), (W, 48)], fill=R["dimred"], width=1)
        title = "ADAPTER REQUIRED"
        tw    = F.getbbox(title)[2]
        d.text(((W-tw)//2, 12), title, font=F, fill=R["red"])

        # pulsing USB box
        amp   = abs((pulse % 50) - 25) / 25.0
        col_p = (int(80 + amp * 175), 0, 0)
        bx, by, bw, bh = W//2-45, 66, 90, 60
        d.rectangle([bx, by, bx+bw, by+bh], fill=R["panel"], outline=col_p)
        usb_w = Fb.getbbox("USB")[2]
        d.text((bx+(bw-usb_w)//2, by+8),  "USB",       font=Fb, fill=col_p)
        sub_w = Fs.getbbox("TL-WN722N")[2]
        d.text((bx+(bw-sub_w)//2, by+30), "TL-WN722N", font=Fs, fill=R["dimwhite"])

        for i, (msg, col) in enumerate([
            ("No adapter detected.",          R["white"]),
            ("Plug in your TL-WN722N",        R["dimwhite"]),
            ("to connect to saved networks.", R["dimwhite"]),
        ]):
            mw = Fs.getbbox(msg)[2]
            d.text(((W-mw)//2, 146 + i*20), msg, font=Fs, fill=col)

        dots  = "." * (1 + (pulse // 10) % 3)
        label = f"Waiting{dots}"
        lw    = Fb.getbbox(label)[2]
        d.text(((W-lw)//2, 220), label, font=Fb, fill=R["dimred"])

        # back hint
        back_label = "TAP ANYWHERE TO GO BACK"
        bw2        = Fs.getbbox(back_label)[2]
        d.rectangle([0, H-28, W, H], fill=R["panel"])
        d.line([(0, H-28), (W, H-28)], fill=R["dimred"], width=1)
        d.text(((W-bw2)//2, H-18), back_label, font=Fs, fill=R["dimred"])

        push(img)
        time.sleep(1/10)
