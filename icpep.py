#!/usr/bin/env python3
"""
ICpEP.SE Recruitment Screen for BearBox
Drop in: /home/bearbox/bearbox/icpep.py
Run:     python /home/bearbox/bearbox/icpep.py

━━━ CONFIGURE HERE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

LINES = [
    # (text,            font_size,  color)               ← color is optional; omit to use BASE/BRIGHT pulse
    ("JOIN",            84),
    ("COMPUTER",        84,         (255, 255, 255)),     # white
    ("ENGINEERING",     84),
]

LINE_SPACING = 12   # px gap between lines

# ── Color config (R, G, B) ─────────────────────────────────────
# The idle and intro animations pulse between BASE_COLOR and BRIGHT_COLOR.
# SHADOW_COLOR is the drop-shadow behind the text.
# GLITCH_COLOR is used for random artifact characters during the intro.

BASE_COLOR   = (0, 130, 220)   # dimmer pulse extreme   — default: cyan-blue
BRIGHT_COLOR = (0, 255, 255)   # brighter pulse extreme — default: bright cyan
SHADOW_COLOR = (0,  10,  25)   # drop shadow            — default: near-black
GLITCH_COLOR = (0,  55,  85)   # intro glitch artifacts — default: dark cyan

"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import time, os, sys, math, random, string, subprocess, signal

sys.path.insert(0, "/home/bearbox/bearbox/core")
from display import new_frame, push, font, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap

BLACK        = (0, 0, 0)
GLITCH_CHARS = list(string.ascii_uppercase + string.digits + "@#$%&!?|/<>[]")

# ── Color interpolation helper ────────────────────────────────
def _lerp_color(a, b, t):
    """Linearly interpolate between two RGB tuples by factor t (0.0–1.0)."""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

# ── Build fonts from config ────────────────────────────────────
_built = []
def _build_fonts():
    global _built
    if not _built:
        _built = [(row[0], font(row[1], bold=True), row[2] if len(row) > 2 else None)
                  for row in LINES]
    return _built

# ── Service control ───────────────────────────────────────────
def _stop_service():
    subprocess.run(["sudo", "systemctl", "stop", "bearbox"], capture_output=True)

def _start_service():
    subprocess.run(["sudo", "systemctl", "start", "bearbox"], capture_output=True)

# ── Layout helper — centered block ───────────────────────────
def _layout(lines_fonts):
    """Return list of (txt, fnt, x, y, th, line_color) centered on screen."""
    total_h = sum(fnt.getbbox(txt)[3] for txt, fnt, _ in lines_fonts)
    total_h += LINE_SPACING * (len(lines_fonts) - 1)
    y = (H - total_h) // 2
    result = []
    for txt, fnt, line_color in lines_fonts:
        th = fnt.getbbox(txt)[3]
        tw = fnt.getbbox(txt)[2]
        x  = (W - tw) // 2
        result.append((txt, fnt, x, y, th, line_color))
        y += th + LINE_SPACING
    return result

# ── CRT shutdown animation ────────────────────────────────────
def _play_shutdown():
    start = time.time()
    small = font(13)
    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.5:
            progress = t / 0.5
            for _ in range(int(progress * 20) + 3):
                y   = random.randint(0, H)
                h   = random.randint(1, 6)
                alp = random.randint(20, 120)
                d.rectangle([0, y, W, y + h], fill=(0, alp, int(alp * 1.8)))
            for _ in range(int(progress * 200)):
                a = random.randint(10, 60)
                d.point((random.randint(0, W), random.randint(0, H)),
                        fill=(0, a, int(a * 1.5)))

        elif t < 1.0:
            progress = (t - 0.5) / 0.5
            ease     = 1 - (1 - progress) ** 3
            band_h   = max(1, int(H * (1 - ease)))
            cy       = H // 2
            top, bot = cy - band_h // 2, cy + band_h // 2
            bright   = int(200 + ease * 55)
            d.rectangle([0, top, W, bot],
                         fill=(0, bright, min(255, int(bright * 1.3))))
            for _ in range(4):
                ny = random.randint(top, max(top, bot - 1))
                d.line([(0, ny), (W, ny)], fill=(0, min(255, bright + 40), 255))

        elif t < 1.3:
            progress = (t - 1.0) / 0.3
            line_w   = max(2, int(W * (1 - progress ** 2)))
            cx, cy   = W // 2, H // 2
            bright   = int(255 * (1 - progress * 0.5))
            d.rectangle([cx - line_w // 2, cy - 1,
                          cx + line_w // 2, cy + 1],
                         fill=(0, bright, min(255, int(bright * 1.3))))

        elif t < 1.8:
            pass

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Glitch resolve intro ───────────────────────────────────────
def _play_intro():
    lines_fonts = _build_fonts()
    layout      = _layout(lines_fonts)
    small       = font(13)
    start       = time.time()

    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.3:
            pass

        elif t < 2.5:
            resolved = ((t - 0.3) / 2.2) ** 0.4
            pulse    = (math.sin(t * 8) + 1) / 2

            for txt, fnt, x, y, th, line_color in layout:
                display = ""
                for i, ch in enumerate(txt):
                    char_r = max(0.0, resolved - (i / len(txt)) * 0.4)
                    display += ch if random.random() < char_r else random.choice(GLITCH_CHARS)

                tw  = fnt.getbbox(display)[2]
                cx  = (W - tw) // 2

                # Use per-line color if set, otherwise pulse between BASE/BRIGHT
                if line_color is not None:
                    col = tuple(int(c * min(1.0, resolved + pulse * 0.15)) for c in line_color)
                else:
                    t_factor = min(1.0, resolved + pulse * 0.15)
                    col = _lerp_color(BASE_COLOR, BRIGHT_COLOR, t_factor)

                d.text((cx + 2, y + 2), display, font=fnt, fill=SHADOW_COLOR)
                d.text((cx, y),         display, font=fnt, fill=col)

                if resolved < 0.9:
                    artifact = "".join(random.choice(GLITCH_CHARS)
                                       for _ in range(random.randint(1, 3)))
                    aa = int((1 - resolved) * 55)
                    gc = tuple(min(255, int(GLITCH_COLOR[i] * (aa / 55))) for i in range(3))
                    d.text((random.randint(10, W - 60),
                            y + random.randint(-10, th)),
                           artifact, font=small, fill=gc)

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Idle draw ─────────────────────────────────────────────────
def _draw_idle(d):
    pulse       = (math.sin(time.time() * 2.0) + 1) / 2
    lines_fonts = _build_fonts()
    layout      = _layout(lines_fonts)
    pulse_col   = _lerp_color(BASE_COLOR, BRIGHT_COLOR, pulse)

    for txt, fnt, x, y, th, line_color in layout:
        col = line_color if line_color is not None else pulse_col
        d.text((x + 2, y + 2), txt, font=fnt, fill=SHADOW_COLOR)
        d.text((x, y),         txt, font=fnt, fill=col)

# ── Cleanup ───────────────────────────────────────────────────
def _cleanup(sig=None, frame=None):
    print("\n[icpep] restoring bearbox...")
    for _ in range(15):
        img, d = new_frame(bg=BLACK)
        push(img)
        time.sleep(1 / 30)
    _start_service()
    sys.exit(0)

signal.signal(signal.SIGINT,  _cleanup)
signal.signal(signal.SIGTERM, _cleanup)

# ── Entry ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[icpep] lines:", [(row[0], row[1]) for row in LINES])
    print("[icpep] stopping bearbox...")
    _stop_service()
    time.sleep(0.3)

    _play_shutdown()
    _play_intro()

    print("[icpep] running — Ctrl+C or tap to exit")
    while True:
        img, d = new_frame(bg=BLACK)
        _draw_idle(d)
        push(img)

        _net_utils._last_tap = 0
        if check_tap():
            _cleanup()

        time.sleep(1 / 30)