#!/usr/bin/env python3
"""
BearBox — CAMERA CONNECTED Screen
Amber variant of the connected screens.
Plays when a USB camera is detected.
"""

import os
import sys
import time
import random
import string

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H

DURATION         = 3.0
LINE1            = "CAMERA"
LINE2            = "CONNECTED"
MAIN_SIZE        = 72
CREDIT           = "starting surveillance..."
CREDIT_SIZE      = 16
BG_SIZE          = 10
GLITCH_CHANCE    = 0.12
GLITCH_INTENSITY = 8

A = {
    "bg":       (0,    5,   15),
    "amber":    (255, 176,   0),
    "dimamber": (120,  70,   0),
    "darkamber":(20,   10,   0),
    "white":    (240, 248, 255),
    "glow":     (30,   15,   0),
    "ghost":    (80,   40,   0),
    "scan":     (0,    5,   15),
}

_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")

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
            if random.random() < 0.06:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in self.chars):
            self._reset()
    def draw(self, d, fnt):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                d.text((self.x, y), c["char"], font=fnt, fill=(60, 30, 0))

_glitch_active  = False
_glitch_timer   = 0.0
_glitch_offset  = (0, 0)
_glitch_color   = None

def _update_glitch():
    global _glitch_active, _glitch_timer, _glitch_offset, _glitch_color
    now = time.time()
    if not _glitch_active:
        if random.random() < GLITCH_CHANCE:
            _glitch_active = True
            _glitch_timer  = now
            _glitch_offset = (
                random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY),
                random.randint(-2, 2)
            )
            _glitch_color = random.choice([
                (255, 200,   0),
                (255, 140,   0),
                (255, 220, 100),
            ])
    else:
        if now - _glitch_timer > random.uniform(0.05, 0.15):
            _glitch_active = False

_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%")

def run():
    F    = font(MAIN_SIZE, bold=True)
    Fc   = font(CREDIT_SIZE)
    Fbg  = font(BG_SIZE)
    cols = [_BgCol(int((i + 0.5) * W / 16)) for i in range(16)]
    start = time.time()

    while True:
        now      = time.time()
        progress = min((now - start) / DURATION, 1.0)
        if progress >= 1.0:
            break

        _update_glitch()
        for col in cols:
            col.update()

        # fade out last 25%
        if progress > 0.75:
            alpha = 1.0 - (progress - 0.75) / 0.25
        else:
            alpha = 1.0

        img, d = new_frame(bg=A["bg"])
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(0, 5, 15))
        for col in cols:
            col.draw(d, Fbg)

        # resolve text
        def resolve(text, t):
            result = ""
            for i, ch in enumerate(text):
                lp = max(0.0, min(1.0, (t - (i / len(text)) * 0.3) * 3))
                if lp >= 1.0:
                    result += ch
                elif lp > 0:
                    result += ch if random.random() < lp else random.choice(_CHARS)
                else:
                    result += random.choice(_CHARS)
            return result

        r1 = resolve(LINE1, progress * 1.5)
        r2 = resolve(LINE2, (progress - 0.15) * 1.5)

        F1w = F.getbbox(r1)[2]
        F2w = F.getbbox(r2)[2]
        F1h = F.getbbox(r1)[3]
        F2h = F.getbbox(r2)[3]
        gap = 10
        total_h = F1h + gap + F2h
        lx1 = (W - F1w) // 2
        ly1 = (H - total_h) // 2 - 20
        lx2 = (W - F2w) // 2
        ly2 = ly1 + F1h + gap

        if _glitch_active:
            lx1 += _glitch_offset[0]; ly1 += _glitch_offset[1]
            lx2 += _glitch_offset[0]; ly2 += _glitch_offset[1]
            ghost = A["ghost"]
            d.text((lx1 + 3, ly1 + 1), r1, font=F, fill=ghost)
            d.text((lx2 - 3, ly2 - 1), r2, font=F, fill=ghost)
            col1 = col2 = _glitch_color
        else:
            col1 = tuple(int(c * alpha) for c in A["amber"])
            col2 = tuple(int(c * alpha) for c in A["white"])

        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            d.text((lx1+ox, ly1+oy), r1, font=F, fill=A["glow"])
            d.text((lx2+ox, ly2+oy), r2, font=F, fill=A["glow"])

        d.text((lx1, ly1), r1, font=F, fill=col1)
        d.text((lx2, ly2), r2, font=F, fill=col2)

        ul_y = ly2 + F2h + 6
        d.line([(lx2, ul_y), (lx2 + F2w, ul_y)], fill=A["dimamber"], width=2)

        # credit
        if progress > 0.5:
            a   = min(1.0, (progress - 0.5) / 0.3) * alpha
            cw  = Fc.getbbox(CREDIT)[2]
            d.text(((W - cw) // 2, ly2 + F2h + 20),
                   CREDIT, font=Fc,
                   fill=tuple(int(c * a) for c in A["dimamber"]))

        push(img)
        time.sleep(1 / 30)

    img, _ = new_frame(bg=A["bg"])
    push(img)
    time.sleep(0.1)


if __name__ == "__main__":
    run()