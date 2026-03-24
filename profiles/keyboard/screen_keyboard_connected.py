#!/usr/bin/env python3
"""
BearBox — KEYBOARD CONNECTED Screen
Pink variant of screen_connected.py.
Plays when a USB keyboard is detected.
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

DURATION         = 3.5
LINE1            = "KEYBOARD"
LINE2            = "CONNECTED"
MAIN_SIZE        = 72
CREDIT           = "loading terminal..."
CREDIT_SIZE      = 16
BG_SIZE          = 10
GLITCH_CHANCE    = 0.12
GLITCH_INTENSITY = 8

# Pink palette
P = {
    "bg_start": (18,  0,  18),
    "bg_end":   (8,   0,  18),
    "text":     (255, 0,  180),
    "text2":    (220, 80, 200),
    "glow":     (30,  0,  30),
    "ghost":    (80,  0,  80),
    "underline":(180, 0,  140),
    "credit":   (100, 20, 90),
    "scan":     (8,   0,  18),
    "bg_char":  (60,  0,  50),
}

_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")
_CHARS    = list(string.ascii_uppercase + string.digits + "!@#$%")


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

    def draw(self, d, fnt):
        for c in self.chars:
            y = int(c["y"])
            if 0 <= y <= H:
                d.text((self.x, y), c["char"], font=fnt, fill=P["bg_char"])


def _lerp(a, b, t):
    return int(a + (b - a) * t)


def run():
    F    = font(MAIN_SIZE, bold=True)
    Fc   = font(CREDIT_SIZE)
    Fbg  = font(BG_SIZE)
    cols = [_BgCol(int((i + 0.5) * W / 20)) for i in range(20)]
    start = time.time()

    while True:
        now      = time.time()
        progress = min((now - start) / DURATION, 1.0)
        if progress >= 1.0:
            break

        for col in cols:
            col.update()

        t = progress * progress * (3 - 2 * progress)

        img, d = new_frame(bg=P["bg_end"])

        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=P["scan"])

        for col in cols:
            col.draw(d, Fbg)

        # glitch lines
        if random.random() < GLITCH_CHANCE:
            for _ in range(random.randint(1, 3)):
                gy = random.randint(0, H)
                gx = random.randint(0, W // 2)
                gw = random.randint(20, 120)
                d.line([(gx, gy), (gx + gw, gy)],
                       fill=(int(255 * t), 0, int(180 * t)), width=1)

        # LINE1
        def resolve(text, t_offset):
            result = ""
            for i, ch in enumerate(text):
                lp = max(0.0, min(1.0, (t - t_offset - (i / len(text)) * 0.3) * 3))
                if lp >= 1.0:
                    result += ch
                elif lp > 0:
                    result += ch if random.random() < lp else random.choice(_CHARS)
                else:
                    result += random.choice(_CHARS)
            return result

        r1 = resolve(LINE1, 0.0)
        r2 = resolve(LINE2, 0.1)

        lw1 = F.getbbox(r1)[2]
        lh1 = F.getbbox(r1)[3]
        lw2 = F.getbbox(r2)[2]
        lh2 = F.getbbox(r2)[3]

        gap     = 8
        total_h = lh1 + gap + lh2
        lx1     = (W - lw1) // 2
        ly1     = H // 2 - total_h // 2 - 14
        lx2     = (W - lw2) // 2
        ly2     = ly1 + lh1 + gap

        # ghost glitch
        if random.random() < GLITCH_CHANCE * 0.5:
            ox = random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY)
            d.text((lx1 + ox, ly1 + 2), r1, font=F, fill=P["ghost"])
            d.text((lx2 + ox, ly2 + 2), r2, font=F, fill=P["ghost"])

        # glow
        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            d.text((lx1 + ox, ly1 + oy), r1, font=F, fill=P["glow"])
            d.text((lx2 + ox, ly2 + oy), r2, font=F, fill=P["glow"])

        d.text((lx1, ly1), r1, font=F, fill=P["text"])
        d.text((lx2, ly2), r2, font=F, fill=P["text2"])

        # underline under LINE2
        d.line([(lx2, ly2 + lh2 + 4), (lx2 + lw2, ly2 + lh2 + 4)],
               fill=P["underline"], width=2)

        # credit
        cw = Fc.getbbox(CREDIT)[2]
        d.text(((W - cw) // 2, ly2 + lh2 + 18), CREDIT,
               font=Fc, fill=P["credit"])

        push(img)
        time.sleep(1 / 30)

    # hold on final frame
    img, d = new_frame(bg=P["bg_end"])
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=P["scan"])
    lw1 = F.getbbox(LINE1)[2]
    lh1 = F.getbbox(LINE1)[3]
    lw2 = F.getbbox(LINE2)[2]
    lh2 = F.getbbox(LINE2)[3]
    gap  = 8
    total_h = lh1 + gap + lh2
    ly1 = H // 2 - total_h // 2 - 14
    ly2 = ly1 + lh1 + gap
    d.text(((W - lw1) // 2, ly1), LINE1, font=F, fill=P["text"])
    d.text(((W - lw2) // 2, ly2), LINE2, font=F, fill=P["text2"])
    push(img)
    time.sleep(0.8)


if __name__ == "__main__":
    run()
