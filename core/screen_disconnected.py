#!/usr/bin/env python3
"""
BearBox — DISCONNECTED Screen
Plays when internet is lost.
Blue → Red color transition with glitch effects.
Reverse of screen_connected.py
"""

import os
import sys
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H

DURATION         = 3.5
LINE1            = "DISCONNECTED"
MAIN_SIZE        = 66     # slightly smaller to fit longer word
CREDIT           = "going offline..."
CREDIT_SIZE      = 16
BG_SIZE          = 10
GLITCH_CHANCE    = 0.14
GLITCH_INTENSITY = 10

_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()
    def _reset(self):
        self.speed = random.uniform(2, 5)
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
    def draw(self, d, fnt, progress):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                # transition from blue chars to red chars
                r = int(60 * progress)
                b = int(60 * (1.0 - progress))
                d.text((self.x, y), c["char"], font=fnt, fill=(r, 0, b))

def _lerp(a, b, t):
    return int(a + (b - a) * t)

def _lerp_col(c1, c2, t):
    return (_lerp(c1[0], c2[0], t),
            _lerp(c1[1], c2[1], t),
            _lerp(c1[2], c2[2], t))

_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%")

def run():
    F      = font(MAIN_SIZE, bold=True)
    Fc     = font(CREDIT_SIZE, bold=False)
    Fbg    = font(BG_SIZE)
    cols   = [_BgCol(int((i+0.5)*W/20)) for i in range(20)]
    start  = time.time()

    while True:
        now      = time.time()
        progress = min((now - start) / DURATION, 1.0)
        if progress >= 1.0:
            break

        for col in cols:
            col.update()

        t = progress * progress * (3 - 2 * progress)

        # background: dark blue → dark red
        bg = (_lerp(0, 15, t), 0, _lerp(20, 0, t))

        img, d = new_frame(bg=bg)

        # scanlines
        scan_col = (_lerp(0, 18, t), 0, _lerp(18, 0, t))
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=scan_col)

        for col in cols:
            col.draw(d, Fbg, t)

        # glitch scan lines
        if random.random() < GLITCH_CHANCE:
            for _ in range(random.randint(1, 4)):
                gy   = random.randint(0, H)
                gx   = random.randint(0, W//2)
                gw   = random.randint(20, 120)
                gb   = int(255 * (1-t))
                gr   = int(255 * t)
                d.line([(gx, gy), (gx+gw, gy)], fill=(gr, 0, gb), width=1)

        # main text
        result = ""
        for i, ch in enumerate(LINE1):
            lp = max(0.0, min(1.0, (t - (i/len(LINE1))*0.3) * 3))
            if lp >= 1.0:
                result += ch
            elif lp > 0:
                result += ch if random.random() < lp else random.choice(_CHARS)
            else:
                result += random.choice(_CHARS)

        # color: blue/white → red
        text_col = _lerp_col((100, 200, 255), (255, 40, 40), t)
        lw = F.getbbox(result)[2]
        lh = F.getbbox(result)[3]
        lx = (W - lw) // 2
        ly = H // 2 - lh // 2 - 14

        # ghost glitch
        if random.random() < GLITCH_CHANCE * 0.5:
            ox        = random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY)
            ghost_col = _lerp_col((0, 30, 80), (80, 0, 0), t)
            d.text((lx+ox, ly+2), result, font=F, fill=ghost_col)

        # glow
        glow = _lerp_col((0, 10, 40), (30, 0, 0), t)
        for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
            d.text((lx+ox, ly+oy), result, font=F, fill=glow)

        d.text((lx, ly), result, font=F, fill=text_col)

        # underline
        ul_col = _lerp_col((0, 100, 200), (120, 0, 0), t)
        d.line([(lx, ly+lh+4), (lx+lw, ly+lh+4)], fill=ul_col, width=2)

        # credit
        cw = Fc.getbbox(CREDIT)[2]
        cx = (W - cw) // 2
        cy = ly + lh + 18
        cc = _lerp_col((40, 120, 200), (100, 20, 20), t)
        d.text((cx, cy), CREDIT, font=Fc, fill=cc)

        push(img)
        time.sleep(1/30)

    # hold on final red frame
    img, d = new_frame(bg=(15, 0, 0))
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))
    lw = F.getbbox(LINE1)[2]
    lh = F.getbbox(LINE1)[3]
    d.text(((W-lw)//2, H//2-lh//2-14), LINE1, font=F, fill=(255, 40, 40))
    push(img)
    time.sleep(0.8)

if __name__ == "__main__":
    run()
