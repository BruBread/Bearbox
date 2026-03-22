#!/usr/bin/env python3
"""
BearBox AP — SIPHON ACTIVATED Intro Screen
Matrix rain resolves into "SIPHON ACTIVATED" in magenta.
"""

import os
import sys
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.."))
from display import new_frame, push, font, W, H
from profiles.wifi.ap.ap_utils import C, fonts, draw_scanlines_pink

_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()

    def _reset(self):
        self.speed = random.uniform(2, 5)
        self.chars = [{
            "char": random.choice(_BG_CHARS),
            "y":    random.randint(-H, 0) - i * 12,
        } for i in range(random.randint(4, 10))]

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
                d.text((self.x, y), c["char"], font=fnt, fill=(60, 0, 50))

DURATION      = 3.5
HOLD_START    = 0.55
HOLD_END      = 0.82
RESOLVE_START = 0.20
LINE1         = "SIPHON"
LINE2         = "ACTIVATED"
_CHARS        = list(string.ascii_uppercase + string.digits + "!@#$%")

def _draw_logo(d, F, reveal_pct, alpha=1.0):
    def th(t): return F["huge"].getbbox(t)[3] - F["huge"].getbbox(t)[1]

    total_h = th(LINE1) + 10 + th(LINE2)
    l1_y    = H // 2 - total_h // 2
    l2_y    = l1_y + th(LINE1) + 10

    for line, y in [(LINE1, l1_y), (LINE2, l2_y)]:
        result = ""
        for i, ch in enumerate(line):
            lp = (reveal_pct - (i / len(line)) * 0.4) * 2.5
            lp = max(0.0, min(1.0, lp))
            if lp >= 1.0:
                result += ch
            elif lp > 0:
                result += ch if random.random() < lp else random.choice(_CHARS)
            else:
                result += random.choice(_CHARS)

        a   = int(255 * alpha)
        col = (a, 0, int(180 * alpha)) if line == LINE1 \
              else (int(220 * alpha), int(80 * alpha), int(200 * alpha))
        lw  = F["huge"].getbbox(result)[2]
        d.text(((W - lw) // 2, y), result, font=F["huge"], fill=col)

        if reveal_pct > 0.7:
            ua = int(alpha * min(1.0, (reveal_pct - 0.7) / 0.3) * 180)
            cx = W // 2
            d.line([(cx - lw//2, y + th(line) + 4),
                    (cx + lw//2, y + th(line) + 4)],
                   fill=(ua, 0, int(ua * 0.7)), width=1)

_played = False

def run():
    global _played
    if _played:
        return
    _played = True

    F      = fonts()
    bg_fnt = font(10)
    cols   = [_BgCol(int((i + 0.5) * W / 20)) for i in range(20)]
    start  = time.time()

    while True:
        now      = time.time()
        progress = (now - start) / DURATION
        if progress >= 1.0:
            break

        for col in cols:
            col.update()

        alpha = 1.0
        if progress > HOLD_END:
            alpha = max(0.0, 1.0 - (progress - HOLD_END) / (1.0 - HOLD_END))

        img, d = new_frame(bg=C["bg"])
        draw_scanlines_pink(d)
        for col in cols:
            col.draw(d, bg_fnt)

        if progress > RESOLVE_START * 0.3:
            rp = (progress - RESOLVE_START * 0.3) / (HOLD_START - RESOLVE_START * 0.3)
            rp = max(0.0, min(1.0, rp))
            _draw_logo(d, F, rp, alpha)

        push(img)
        time.sleep(1 / 30)

    img, _ = new_frame(bg=C["bg"])
    push(img)
    time.sleep(0.1)

if __name__ == "__main__":
    run()
