#!/usr/bin/env python3
"""
BearBox — ICpEP.SE Recruitment Screen
Run standalone: python icpep.py
Or drop into idle/SCREENS list for tap-cycling.

Returns (SCREEN PROTOCOL):
  True  — tap outside any button → idle_main cycles
  False — busy or button hit → do NOT cycle
  None  — no tap → idle_main does its own check_tap()
"""

import time, os, sys, math, random, string
sys.path.insert(0, "/home/bearbox/bearbox/core")
from display import new_frame, push, draw_scanlines, font, C, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap, tapped

# Flush any stale taps from before this screen was entered
_net_utils._last_tap = time.time()

# ── Fonts ─────────────────────────────────────────────────────
_F = {}
def _fonts():
    if not _F:
        _F["big"]   = font(28, bold=True)
        _F["title"] = font(22, bold=True)
        _F["body"]  = font(16, bold=True)
        _F["small"] = font(13)
        _F["tiny"]  = font(11)
    return _F

# ── Matrix rain background (same style as hello.py) ───────────
_BG_CHARS = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")
_BG_COLS  = []
_bg_init  = False

def _init_bg(F):
    global _BG_COLS
    col_w    = W // 14
    _BG_COLS = []
    for i in range(14):
        x = i * col_w + col_w // 2
        _BG_COLS.append({
            "x": x,
            "chars": [{
                "char":  random.choice(_BG_CHARS),
                "y":     random.randint(-H, 0) - j * 12,
                "alpha": random.randint(10, 40),
                "speed": random.uniform(0.3, 0.9),
            } for j in range(random.randint(4, 10))]
        })

def _update_bg():
    for col in _BG_COLS:
        for c in col["chars"]:
            c["y"] += c["speed"]
            if random.random() < 0.04:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in col["chars"]):
            y = random.randint(-H // 2, 0)
            col["chars"] = [{
                "char":  random.choice(_BG_CHARS),
                "y":     y - j * 12,
                "alpha": random.randint(10, 40),
                "speed": random.uniform(0.3, 0.9),
            } for j in range(random.randint(4, 10))]

def _draw_bg(d, F):
    for col in _BG_COLS:
        for c in col["chars"]:
            if 0 <= c["y"] <= H:
                a = c["alpha"]
                d.text((col["x"], int(c["y"])), c["char"],
                       font=F["tiny"], fill=(0, a, int(a * 1.5)))

# ── Glitch effect — random horizontal bar flickers ────────────
_glitch_timer = 0.0
_glitch_bars  = []

def _tick_glitch():
    global _glitch_timer, _glitch_bars
    now = time.time()
    if now > _glitch_timer:
        # Schedule next glitch burst
        _glitch_timer = now + random.uniform(0.4, 1.8)
        count = random.randint(1, 4)
        _glitch_bars = [{
            "y":     random.randint(40, H - 20),
            "h":     random.randint(1, 4),
            "alpha": random.randint(30, 80),
            "w":     random.randint(W // 4, W),
            "x":     random.randint(0, W // 3),
        } for _ in range(count)]
    else:
        _glitch_bars = []

def _draw_glitch(d):
    for bar in _glitch_bars:
        a = bar["alpha"]
        d.rectangle(
            [bar["x"], bar["y"], bar["x"] + bar["w"], bar["y"] + bar["h"]],
            fill=(0, a, int(a * 1.5))
        )

# ── Animated text helpers ──────────────────────────────────────
_REVEAL_START = time.time()   # used for typewriter reveal
_TYPEWRITER_SPEED = 12        # chars revealed per second

def _typewriter(text, elapsed):
    """Return the slice of text that should be visible by now."""
    chars = int(elapsed * _TYPEWRITER_SPEED)
    return text[:chars]

# ── Main draw ─────────────────────────────────────────────────
_started = time.time()

def draw():
    """
    SCREEN PROTOCOL:
      True  → tap outside button, cycle
      False → busy / button pressed
      None  → no tap
    """
    global _bg_init, _started

    F = _fonts()
    if not _bg_init:
        _init_bg(F)
        _bg_init = True

    now     = time.time()
    elapsed = now - _started
    pulse   = (math.sin(now * 2.5) + 1) / 2          # 0–1 smooth wave
    blink   = int(now * 1.8) % 2 == 0                 # cursor blink

    _update_bg()
    _tick_glitch()

    img, d = new_frame(bg=C["bg"])
    draw_scanlines(d)
    _draw_bg(d, F)
    _draw_glitch(d)

    # ── Header bar ────────────────────────────────────────────
    d.rectangle([0, 0, W, 38], fill=C["panel"])
    d.line([(0, 38), (W, 38)], fill=C["dimblue"], width=1)
    hdr  = "ICpEP.SE"
    hdrw = F["title"].getbbox(hdr)[2]
    d.text(((W - hdrw) // 2, 7), hdr, font=F["title"], fill=C["blue"])

    # ── "JOIN COMPUTER ENGINEERING" — typewriter reveal ───────
    line1 = "JOIN COMPUTER"
    line2 = "ENGINEERING"
    full  = line1 + " " + line2
    shown = _typewriter(full, elapsed - 0.3)   # slight delay after screen load

    # Split shown back across two lines
    shown1 = shown[:len(line1)]
    shown2 = shown[len(line1)+1:] if len(shown) > len(line1) else ""

    # Pulse the color: cycles between blue and bright white
    r_val = int(pulse * 80)
    g_val = int(160 + pulse * 95)
    b_val = int(220 + pulse * 35)
    col   = (r_val, g_val, b_val)
    dim   = C["dimblue"]

    y1 = 62
    y2 = 100

    # Line 1
    if shown1:
        cursor1 = "_" if (blink and len(shown) <= len(line1)) else ""
        t1 = shown1 + cursor1
        tw = F["big"].getbbox(t1)[2]
        # Shadow
        d.text(((W - tw) // 2 + 1, y1 + 1), t1, font=F["big"], fill=(0, 20, 40))
        d.text(((W - tw) // 2, y1), t1, font=F["big"], fill=col)

    # Line 2
    if shown2:
        cursor2 = "_" if (blink and len(shown) > len(line1)) else ""
        t2 = shown2 + cursor2
        tw = F["big"].getbbox(t2)[2]
        d.text(((W - tw) // 2 + 1, y2 + 1), t2, font=F["big"], fill=(0, 20, 40))
        d.text(((W - tw) // 2, y2), t2, font=F["big"], fill=col)

    # ── Divider ───────────────────────────────────────────────
    if elapsed > 1.8:
        line_alpha = min(1.0, (elapsed - 1.8) / 0.5)
        la = int(line_alpha * 255)
        d.line([(40, 138), (W - 40, 138)], fill=(0, la // 3, la // 2), width=1)

    # ── Sub-text: org details, fade in ────────────────────────
    if elapsed > 2.0:
        fade = min(1.0, (elapsed - 2.0) / 0.8)
        fw   = int(fade * 160)
        fd   = int(fade * 80)

        lines = [
            ("Institute of Computer Engineers", 148, F["small"], (0, fw, int(fw * 1.4))),
            ("of the Philippines", 166, F["small"], (0, fw, int(fw * 1.4))),
            ("Student Edition", 186, F["tiny"],  (0, fd, int(fd * 1.4))),
        ]
        for txt, y, fnt, clr in lines:
            tw = fnt.getbbox(txt)[2]
            d.text(((W - tw) // 2, y), txt, font=fnt, fill=clr)

    # ── Scanning bar — a bright line that sweeps down ─────────
    scan_y = int((now * 60) % (H + 20)) - 10
    if 0 <= scan_y <= H:
        brightness = int(40 + pulse * 30)
        d.line([(0, scan_y), (W, scan_y)],
               fill=(0, brightness, int(brightness * 1.6)), width=1)

    # ── Hint ──────────────────────────────────────────────────
    hint  = "tap to continue"
    hw    = F["tiny"].getbbox(hint)[2]
    h_col = (0, int(30 + pulse * 25), int(55 + pulse * 35))
    d.text(((W - hw) // 2, H - 14), hint, font=F["tiny"], fill=h_col)

    push(img)

    # ── Touch handling (SCREEN PROTOCOL) ─────────────────────
    if check_tap():
        return True   # tap anywhere → cycle to next screen

    return None       # no tap → idle_main handles its own check


# ── Standalone runner ─────────────────────────────────────────
if __name__ == "__main__":
    print("ICpEP screen — Ctrl+C to quit")
    while True:
        draw()
        time.sleep(1 / 30)
