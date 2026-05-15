#!/usr/bin/env python3
"""
ICpEP.SE Recruitment Screen for BearBox
Drop in: /home/bearbox/bearbox/icpep.py
Run:     python /home/bearbox/bearbox/icpep.py

Kills the current bearbox service, plays a CRT shutdown animation,
fades to black, then shows "JOIN COMPUTER ENGINEERING" in a glitch
resolve animation — big, fullscreen, nothing else.

Ctrl+C or any tap to exit (restarts bearbox service).
"""

import time, os, sys, math, random, string, subprocess, signal

sys.path.insert(0, "/home/bearbox/bearbox/core")
from display import new_frame, push, font, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap

# ── Fonts — as big as possible, split across three lines ──────
_F = {}
def _fonts():
    if not _F:
        _F["huge"]  = font(64, bold=True)   # JOIN
        _F["big"]   = font(52, bold=True)   # COMPUTER
        _F["med"]   = font(44, bold=True)   # ENGINEERING
        _F["small"] = font(13)
    return _F

# ── Colors ────────────────────────────────────────────────────
BLACK       = (0, 0, 0)
GLITCH_CHARS = list(string.ascii_uppercase + string.digits + "@#$%&!?|/<>[]")

# ── Service control ───────────────────────────────────────────
def _stop_service():
    subprocess.run(["sudo", "systemctl", "stop", "bearbox"],
                   capture_output=True)

def _start_service():
    subprocess.run(["sudo", "systemctl", "start", "bearbox"],
                   capture_output=True)

# ── CRT shutdown animation ────────────────────────────────────
def _play_shutdown():
    """
    Phase 1 (0.0-0.5s): screen flickers with noise
    Phase 2 (0.5-1.0s): image compresses vertically to bright line
    Phase 3 (1.0-1.3s): line shrinks horizontally and fades
    Phase 4 (1.3-1.8s): pure black
    """
    start = time.time()
    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.5:
            progress = t / 0.5
            num_bars = int(progress * 20) + 3
            for _ in range(num_bars):
                y   = random.randint(0, H)
                h   = random.randint(1, 6)
                alp = random.randint(20, 120)
                d.rectangle([0, y, W, y + h],
                             fill=(0, alp, int(alp * 1.8)))
            for _ in range(int(progress * 200)):
                x = random.randint(0, W)
                y = random.randint(0, H)
                a = random.randint(10, 60)
                d.point((x, y), fill=(0, a, int(a * 1.5)))

        elif t < 1.0:
            progress = (t - 0.5) / 0.5
            ease     = 1 - (1 - progress) ** 3
            band_h   = max(1, int(H * (1 - ease)))
            cy       = H // 2
            top      = cy - band_h // 2
            bottom   = cy + band_h // 2
            bright   = int(200 + ease * 55)
            d.rectangle([0, top, W, bottom],
                         fill=(0, bright, min(255, int(bright * 1.3))))
            for _ in range(4):
                ny = random.randint(top, max(top, bottom - 1))
                d.line([(0, ny), (W, ny)],
                        fill=(0, min(255, bright + 40), 255))

        elif t < 1.3:
            progress = (t - 1.0) / 0.3
            ease     = progress ** 2
            line_w   = max(2, int(W * (1 - ease)))
            cx       = W // 2
            cy       = H // 2
            bright   = int(255 * (1 - progress * 0.5))
            d.rectangle([cx - line_w // 2, cy - 1,
                          cx + line_w // 2, cy + 1],
                         fill=(0, bright, min(255, int(bright * 1.3))))

        elif t < 1.8:
            pass  # pure black hold

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Glitch resolve intro ───────────────────────────────────────
def _play_intro():
    """
    Phase 1 (0.0-0.3s): black hold
    Phase 2 (0.3-2.5s): scrambled chars resolve left-to-right into real text
    """
    F     = _fonts()
    lines = [
        ("JOIN",        F["huge"]),
        ("COMPUTER",    F["big"]),
        ("ENGINEERING", F["med"]),
    ]
    start = time.time()

    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.3:
            pass

        elif t < 2.5:
            progress = (t - 0.3) / 2.2
            resolved = progress ** 0.4   # fast start, slow finish
            pulse    = (math.sin(t * 8) + 1) / 2

            spacing = 12
            total_h = sum(fnt.getbbox(txt)[3] for txt, fnt in lines) + spacing * (len(lines) - 1)
            y       = (H - total_h) // 2

            for txt, fnt in lines:
                th = fnt.getbbox(txt)[3]

                # Each character resolves individually left-to-right
                display = ""
                for i, ch in enumerate(txt):
                    char_resolve = max(0.0, resolved - (i / len(txt)) * 0.4)
                    if random.random() > char_resolve:
                        display += random.choice(GLITCH_CHARS)
                    else:
                        display += ch

                tw  = fnt.getbbox(display)[2]
                x   = (W - tw) // 2
                g   = int(60 + resolved * 80 + pulse * 20)
                b   = int(100 + resolved * 155 + pulse * 30)
                col = (0, g, b)

                d.text((x + 2, y + 2), display, font=fnt, fill=(0, 10, 25))
                d.text((x, y), display, font=fnt, fill=col)

                # Floating artifact chars while still glitching
                if resolved < 0.9:
                    artifact = "".join(random.choice(GLITCH_CHARS)
                                       for _ in range(random.randint(1, 3)))
                    ax  = random.randint(10, W - 60)
                    ay  = y + random.randint(-10, th)
                    aa  = int((1 - resolved) * 55)
                    d.text((ax, ay), artifact, font=F["small"],
                           fill=(0, aa, int(aa * 1.5)))

                y += th + spacing

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Idle draw — fully resolved, slow pulse ────────────────────
def _draw_idle(d, F):
    now     = time.time()
    pulse   = (math.sin(now * 2.0) + 1) / 2

    lines   = [
        ("JOIN",        F["huge"]),
        ("COMPUTER",    F["big"]),
        ("ENGINEERING", F["med"]),
    ]
    spacing = 12
    total_h = sum(fnt.getbbox(txt)[3] for txt, fnt in lines) + spacing * (len(lines) - 1)
    y       = (H - total_h) // 2

    for txt, fnt in lines:
        th  = fnt.getbbox(txt)[3]
        tw  = fnt.getbbox(txt)[2]
        x   = (W - tw) // 2
        g   = int(130 + pulse * 25)
        b   = int(220 + pulse * 35)
        col = (0, g, b)
        d.text((x + 2, y + 2), txt, font=fnt, fill=(0, 10, 25))
        d.text((x, y), txt, font=fnt, fill=col)
        y += th + spacing

# ── Cleanup / exit ─────────────────────────────────────────────
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
    print("[icpep] stopping bearbox service...")
    _stop_service()
    time.sleep(0.3)

    print("[icpep] CRT shutdown animation...")
    _play_shutdown()

    print("[icpep] glitch intro...")
    _play_intro()

    print("[icpep] running — Ctrl+C or tap to exit")
    F = _fonts()
    while True:
        img, d = new_frame(bg=BLACK)
        _draw_idle(d, F)
        push(img)

        _net_utils._last_tap = 0
        if check_tap():
            _cleanup()

        time.sleep(1 / 30)