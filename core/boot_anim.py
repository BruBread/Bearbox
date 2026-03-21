#!/usr/bin/env python3
"""
BearBox — Boot Animation
Matrix rain gradually resolves into BEARBOX text.
Runs once on startup then hands off to idle_main.
"""

import time
import os
import sys
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, C, W, H

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DURATION      = 5.0    # total animation seconds
HOLD_START    = 0.65   # when BEARBOX is fully revealed — holds here
HOLD_END      = 0.85   # when fade out begins
LOGO_TEXT     = "BEARBOX"
LOGO_SIZE     = 72
TAGLINE       = "hot-swappable pi by FD"
TAGLINE_SIZE  = 14
TAGLINE_OFFSET = 24    # pixels below logo ← increase to move lower
COL_COUNT     = 32
CHAR_SIZE     = 14
RESOLVE_START = 0.25   # when logo starts resolving

# ─────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────
_F = {}

def _fonts():
    if not _F:
        _F["logo"]    = font(LOGO_SIZE,    bold=True)
        _F["tagline"] = font(TAGLINE_SIZE, bold=False)
        _F["rain"]    = font(CHAR_SIZE)
    return _F

# ─────────────────────────────────────────────────────────────
# MATRIX RAIN
# ─────────────────────────────────────────────────────────────
_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|[]{}=+-~")

class RainColumn:
    def __init__(self, x):
        self.x = x
        self._reset()

    def _reset(self):
        self.speed  = random.uniform(3, 8)
        self.length = random.randint(6, 18)
        self.chars  = [{
            "char": random.choice(_CHARS),
            "y":    random.randint(-H, 0) - i * (CHAR_SIZE + 1),
        } for i in range(self.length)]

    def update(self):
        for c in self.chars:
            c["y"] += self.speed
            if random.random() < 0.08:
                c["char"] = random.choice(_CHARS)
        if self.chars[0]["y"] > H + 40:
            self._reset()

    def draw(self, d, F, alpha_mult=1.0):
        for i, c in enumerate(self.chars):
            y = int(c["y"])
            if y < -CHAR_SIZE or y > H:
                continue
            frac = i / max(len(self.chars) - 1, 1)
            if i == 0:
                col = (
                    int(180 * alpha_mult),
                    int(255 * alpha_mult),
                    int(180 * alpha_mult)
                )
            else:
                b = int((1.0 - frac) * 200 * alpha_mult)
                col = (0, b, int(b * 0.4))
            d.text((self.x, y), c["char"], font=F["rain"], fill=col)

# ─────────────────────────────────────────────────────────────
# LOGO
# ─────────────────────────────────────────────────────────────

def _logo_pos(F):
    bbox = F["logo"].getbbox(LOGO_TEXT)
    lw   = bbox[2] - bbox[0]
    lh   = bbox[3] - bbox[1]
    x    = (W - lw) // 2
    y    = (H - lh) // 2 - 20
    return x, y, lw, lh

def _draw_logo(d, F, reveal_pct, alpha_mult=1.0):
    x, y, lw, lh = _logo_pos(F)

    for i, letter in enumerate(LOGO_TEXT):
        # stagger each letter's reveal
        letter_pct = (reveal_pct - (i / len(LOGO_TEXT)) * 0.4) * 2.5
        letter_pct = max(0.0, min(1.0, letter_pct))

        if letter_pct >= 1.0:
            display_char = letter
        elif letter_pct > 0:
            display_char = letter if random.random() < letter_pct else random.choice(_CHARS)
        else:
            display_char = random.choice(_CHARS)

        # x position
        prefix = LOGO_TEXT[:i]
        px = F["logo"].getbbox(prefix)[2] - F["logo"].getbbox(prefix)[0] if prefix else 0

        # color
        if display_char == letter and letter_pct > 0.8:
            a = int(255 * alpha_mult)
            col = (0, int(180 * alpha_mult), a) if i % 2 == 0 else (a, a, a)
        else:
            b = int(200 * alpha_mult)
            col = (0, b, int(b * 0.4))

        d.text((x + px, y), display_char, font=F["logo"], fill=col)

    # tagline — lower position using TAGLINE_OFFSET
    if reveal_pct > 0.6:
        tag_alpha = min(1.0, (reveal_pct - 0.6) / 0.4) * alpha_mult
        ta        = int(tag_alpha * 180)
        tag_bbox  = F["tagline"].getbbox(TAGLINE)
        tag_w     = tag_bbox[2] - tag_bbox[0]
        tag_x     = (W - tag_w) // 2
        tag_y     = y + lh + TAGLINE_OFFSET    # ← controlled by config
        d.text((tag_x, tag_y), TAGLINE, font=F["tagline"],
               fill=(int(ta * 0.4), int(ta * 0.7), ta))
        d.line([(tag_x, tag_y + TAGLINE_SIZE + 3),
                (tag_x + tag_w, tag_y + TAGLINE_SIZE + 3)],
               fill=(0, int(ta * 0.4), int(ta * 0.6)), width=1)

# ─────────────────────────────────────────────────────────────
# MAIN — only runs once, no loop issues
# ─────────────────────────────────────────────────────────────
_played = False   # guard so it never plays twice

def play():
    global _played
    if _played:
        return
    _played = True

    F     = _fonts()
    cols  = [RainColumn(int((i + 0.5) * W / COL_COUNT)) for i in range(COL_COUNT)]
    start = time.time()

    while True:
        now      = time.time()
        elapsed  = now - start
        progress = elapsed / DURATION

        if progress >= 1.0:
            break

        for col in cols:
            col.update()

        img, d = new_frame(bg=(0, 0, 0))

        # fade out multiplier
        if progress > HOLD_END:
            alpha_mult = 1.0 - (progress - HOLD_END) / (1.0 - HOLD_END)
            alpha_mult = max(0.0, alpha_mult)
        else:
            alpha_mult = 1.0

        # rain fades as logo resolves, but stays during hold
        if progress > RESOLVE_START and progress < HOLD_START:
            rain_alpha = 1.0 - ((progress - RESOLVE_START) /
                                (HOLD_START - RESOLVE_START)) * 0.8
        elif progress >= HOLD_START:
            rain_alpha = 0.2
        else:
            rain_alpha = 1.0
        rain_alpha *= alpha_mult

        for col in cols:
            col.draw(d, F, alpha_mult=rain_alpha)

        # logo
        if progress > RESOLVE_START * 0.3:
            reveal_pct = (progress - RESOLVE_START * 0.3) / (HOLD_START - RESOLVE_START * 0.3)
            reveal_pct = max(0.0, min(1.0, reveal_pct))
            _draw_logo(d, F, reveal_pct, alpha_mult=alpha_mult)

        push(img)
        time.sleep(1/30)

    # clear
    img, _ = new_frame(bg=(0, 0, 0))
    push(img)
    time.sleep(0.1)


if __name__ == "__main__":
    print("Playing boot animation...")
    play()
    print("Done!")