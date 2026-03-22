#!/usr/bin/env python3
"""
BearBox Network — No Connection Warning Screen
- Terminal noise background
- Animated typewriter message with bullet points
- Clean buttons, no sublabels
Returns: "connect" or "offline"
"""

import os
import sys
import time
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, draw_two_buttons, check_tap, tapped

# ── terminal bg ───────────────────────────────────────────────
_BG_CHARS = list(string.ascii_letters + string.digits + "!@#$%^&*<>/?\\|[]{}=+-")

class _BgCol:
    def __init__(self, x):
        self.x = x
        self._reset()

    def _reset(self):
        self.speed = random.uniform(1.5, 4.0)
        self.chars = [{
            "char": random.choice(_BG_CHARS),
            "y":    random.randint(-H, 0) - i * 12,
        } for i in range(random.randint(4, 10))]

    def update(self):
        for c in self.chars:
            c["y"] += self.speed
            if random.random() < 0.05:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in self.chars):
            self._reset()

    def draw(self, d, fnt):
        for i, c in enumerate(self.chars):
            y = int(c["y"])
            if 0 <= y <= H:
                frac = i / max(len(self.chars) - 1, 1)
                b    = int((1.0 - frac) * 55)
                d.text((self.x, y), c["char"], font=fnt,
                       fill=(0, b, int(b * 0.5)))

# ── message ───────────────────────────────────────────────────
# each entry is a separate line — bullets render differently
_LINES = [
    ("text",   "BEARBOX is not connected to the internet"),
    ("text",   "The following may not properly work:"),
    ("bullet", "Time sync"),
    ("bullet", "Package updates"),
]

# flat string for typewriter — bullets get a prefix
_FULL_TEXT = "\n".join(
    ("  • " + txt) if kind == "bullet" else txt
    for kind, txt in _LINES
)

_TYPE_SPEED = 0.025  # fast typewriter

def run():
    F      = fonts()
    bg_fnt = font(10)
    cols   = [_BgCol(int((i + 0.5) * W / 16)) for i in range(16)]

    btn_w   = 180
    btn_h   = 56
    btn_y   = H - btn_h - 18
    gap     = 16
    left_x  = (W // 2) - btn_w - gap // 2
    right_x = (W // 2) + gap // 2

    start  = time.time()
    pulse  = 0

    while True:
        pulse += 1
        now    = time.time()

        # advance typewriter
        char_i = min(int((now - start) / _TYPE_SPEED), len(_FULL_TEXT))
        typed  = _FULL_TEXT[:char_i]

        img, d = new_frame()

        # terminal bg
        for col in cols:
            col.update()
            col.draw(d, bg_fnt)

        draw_scanlines(d)
        draw_header(d, F, "NO CONNECTION",
                    "internet not detected", color=C["amber"])

        # pulsing ! icon
        amp   = abs((pulse % 60) - 30) / 30.0
        w_col = (255, int(80 + amp * 175), 0)
        iw    = font(36, bold=True).getbbox("!")[2]
        d.text(((W - iw) // 2, 50), "!",
               font=font(36, bold=True), fill=w_col)

        # render typed lines
        lines = typed.split("\n")
        for i, ln in enumerate(lines[:7]):
            is_bullet = ln.startswith("  •")
            col       = C["amber"] if is_bullet else C["white"]
            lw        = F["body"].getbbox(ln)[2]
            # bullets left-align, regular text centered
            x = 24 if is_bullet else (W - lw) // 2
            d.text((x, 96 + i * 22), ln, font=F["body"], fill=col)

        # blinking cursor while typing
        if char_i < len(_FULL_TEXT) and int(now * 6) % 2 == 0 and lines:
            last    = lines[-1]
            lw      = F["body"].getbbox(last)[2]
            is_b    = last.startswith("  •")
            cur_x   = (24 + lw + 2) if is_b else ((W - lw) // 2 + lw + 2)
            cur_y   = 96 + (len(lines) - 1) * 22
            d.rectangle([cur_x, cur_y + 1, cur_x + 6, cur_y + 14],
                        fill=C["amber"])

        # divider
        d.line([(20, btn_y - 14), (W - 20, btn_y - 14)],
               fill=C["dimblue"], width=1)

        # buttons
        l_rect, r_rect = draw_two_buttons(
            d, F, "CONNECT", "GO OFFLINE", C["green"], C["red"]
        )

        push(img)

        if check_tap():
            if tapped(*l_rect):
                return "connect"
            if tapped(*r_rect):
                return "offline"

        time.sleep(1 / 30)