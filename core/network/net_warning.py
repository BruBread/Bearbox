#!/usr/bin/env python3
"""
BearBox Network — No Connection Warning Screen
- Terminal noise background
- Animated typewriter message with bullet points
- 30 second auto-timeout with countdown in top right
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

TIMEOUT = 30  # seconds before auto going offline

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
_LINES = [
    ("text",   "BEARBOX is not connected"),
    ("text",   "to the internet."),
    ("text",   "The following may not"),
    ("text",   "properly work:"),
    ("bullet", "Time sync"),
    ("bullet", "Package updates"),
]

_FULL_TEXT = "\n".join(
    ("  * " + txt) if kind == "bullet" else txt
    for kind, txt in _LINES
)

_TYPE_SPEED = 0.025

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
        now     = time.time()
        elapsed = now - start

        # ── auto timeout ──────────────────────────────────────
        if elapsed >= TIMEOUT:
            return "offline"

        remaining = int(TIMEOUT - elapsed)

        # advance typewriter
        char_i = min(int(elapsed / _TYPE_SPEED), len(_FULL_TEXT))
        typed  = _FULL_TEXT[:char_i]

        img, d = new_frame()

        # terminal bg
        for col in cols:
            col.update()
            col.draw(d, bg_fnt)

        draw_scanlines(d)
        draw_header(d, F, "NO CONNECTION",
                    "internet not detected", color=C["amber"])

        # ── countdown timer top right ─────────────────────────
        # color shifts from blue → amber → red as time runs out
        if remaining > 20:
            timer_col = C["blue"]
        elif remaining > 10:
            timer_col = C["amber"]
        else:
            timer_col = C["red"]

        # draw circle-ish countdown
        timer_str = f"{remaining}s"
        tw = F["big"].getbbox(timer_str)[2]
        tx = W - tw - 10
        ty = 10
        # dim background pill
        d.rectangle([tx - 6, ty - 2, tx + tw + 6, ty + 22],
                    fill=C["panel"], outline=timer_col)
        d.text((tx, ty), timer_str, font=F["big"], fill=timer_col)

        # pulsing ! icon
        amp   = abs((pulse % 60) - 30) / 30.0
        w_col = (255, int(80 + amp * 175), 0)
        iw    = font(36, bold=True).getbbox("!")[2]
        d.text(((W - iw) // 2, 50), "!",
               font=font(36, bold=True), fill=w_col)

        # typed message
        lines = typed.split("\n")
        for i, ln in enumerate(lines[:7]):
            is_bullet = ln.startswith("  *")
            col       = C["amber"] if is_bullet else C["white"]
            # replace * with bullet character
            display   = ln.replace("  *", "  •")
            lw        = F["body"].getbbox(display)[2]
            x = 24 if is_bullet else (W - lw) // 2
            d.text((x, 96 + i * 22), display, font=F["body"], fill=col)

        # blinking cursor
        if char_i < len(_FULL_TEXT) and int(now * 6) % 2 == 0 and lines:
            last    = lines[-1].replace("  *", "  •")
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

        # auto offline hint
        hint = f"Auto offline in {remaining}s"
        hw   = F["small"].getbbox(hint)[2]
        d.text(((W - hw) // 2, btn_y + btn_h + 4),
               hint, font=F["small"], fill=C["dimblue"])

        push(img)

        if check_tap():
            if tapped(*l_rect):
                return "connect"
            if tapped(*r_rect):
                return "offline"

        time.sleep(1 / 30)
