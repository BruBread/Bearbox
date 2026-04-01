#!/usr/bin/env python3
"""
BearBox Idle — HELLO LOSER Screensaver
- Giant centered text with glitch/flicker effect
- Hacking terminal noise in background
- Blue and white color scheme

If a newer commit exists on GitHub:
  - Shows a "PRESS HERE TO UPDATE" button where LINE2 normally sits
  - Tapping it runs `git pull` and restarts the bearbox service
"""

import time
import os
import sys
import math
import random
import string
import subprocess
import threading
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import check_tap, tapped

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

LINE1      = "NO MODULES"        # first line text
LINE2      = "DETECTED"          # second line text (shown when up-to-date)
CREDIT     = "-FD"               # credit text

MAIN_SIZE   = 90             # main text font size
CREDIT_SIZE = 18             # credit font size
BG_SIZE     = 10             # background terminal text size

# ── Position (0.5 = center, 0.0 = left/top, 1.0 = right/bottom)
TEXT_X      = 0.5            # horizontal position (0.0 - 1.0)
TEXT_Y      = 0.4            # vertical position (0.0 - 1.0)
CREDIT_X    = 0.97           # credit horizontal position
CREDIT_Y    = 0.92           # credit vertical position
LINE_GAP    = 8              # gap between LINE1 and LINE2

# ── Glitch settings
GLITCH_CHANCE    = 0.08      # chance of glitch per frame
GLITCH_INTENSITY = 6         # max pixel offset during glitch
FLICKER_CHANCE   = 0.04      # chance of full flicker per frame

# ── Background terminal settings
BG_COLS     = 12             # number of background columns

# ── Update check settings
REPO_OWNER            = "BruBread"
REPO_NAME             = "Bearbox"
BRANCH                = "main"
REPO_PATH             = "/home/bearbox/bearbox"
UPDATE_CHECK_INTERVAL = 250    # re-check every 5 minutes

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

_F = {}

def _fonts():
    if not _F:
        _F["main"]   = font(MAIN_SIZE,   bold=True)
        _F["credit"] = font(CREDIT_SIZE, bold=True)
        _F["bg"]     = font(BG_SIZE)
        _F["btn"]    = font(20,          bold=True)
        _F["sub"]    = font(14)
    return _F

# ── TERMINAL BACKGROUND ───────────────────────────────────────
_BG_CHARS = list(string.ascii_letters + string.digits + "!@#$%^&*<>/?\\|[]{}=+-")
_BG_COLS  = []

def _init_bg(F):
    global _BG_COLS
    col_w  = W // BG_COLS
    _BG_COLS = []
    for i in range(BG_COLS):
        x = i * col_w + col_w // 2
        y = random.randint(-H, 0)
        _BG_COLS.append({"x": x, "chars": [{
            "char":  random.choice(_BG_CHARS),
            "y":     y + j * (BG_SIZE + 2),
            "alpha": random.randint(20, 80),
            "speed": random.uniform(0.4, 1.2),
        } for j in range(random.randint(4, 12))]})

def _update_bg():
    for col in _BG_COLS:
        for c in col["chars"]:
            c["y"] += c["speed"]
            if random.random() < 0.05:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in col["chars"]):
            y = random.randint(-H // 2, 0)
            col["chars"] = [{
                "char":  random.choice(_BG_CHARS),
                "y":     y + j * (BG_SIZE + 2),
                "alpha": random.randint(20, 80),
                "speed": random.uniform(0.4, 1.2),
            } for j in range(random.randint(4, 12))]

def _draw_bg(d, F):
    for col in _BG_COLS:
        for c in col["chars"]:
            if 0 <= c["y"] <= H:
                a = c["alpha"]
                d.text((col["x"], int(c["y"])),
                       c["char"], font=F["bg"], fill=(0, a, int(a * 1.5)))

# ── GLITCH ────────────────────────────────────────────────────
_glitch_active  = False
_glitch_timer   = 0.0
_glitch_offset  = (0, 0)
_glitch_color   = None
_flicker_active = False

def _update_glitch():
    global _glitch_active, _glitch_timer, _glitch_offset
    global _glitch_color, _flicker_active

    now = time.time()
    _flicker_active = random.random() < FLICKER_CHANCE

    if not _glitch_active:
        if random.random() < GLITCH_CHANCE:
            _glitch_active = True
            _glitch_timer  = now
            _glitch_offset = (
                random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY),
                random.randint(-2, 2)
            )
            _glitch_color = random.choice([
                (0,   220, 255),
                (200, 200, 255),
                (0,   100, 255),
            ])
    else:
        if now - _glitch_timer > random.uniform(0.05, 0.15):
            _glitch_active = False

# ── UPDATE CHECK ──────────────────────────────────────────────
_update_available   = False
_update_checking    = False
_update_last_check  = 0.0
_update_in_progress = False
_update_btn_rect    = None   # (x, y, w, h) — set each frame so tapped() works

def _get_local_sha():
    try:
        r = subprocess.run(
            ["git", "-C", REPO_PATH, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return None

def _get_remote_sha():
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"
        r = subprocess.run(
            ["curl", "-sf", "--max-time", "6", url],
            capture_output=True, text=True, timeout=8
        )
        data = json.loads(r.stdout)
        return data.get("sha", "")
    except Exception:
        return None

def _check_update_thread():
    global _update_available, _update_checking, _update_last_check
    _update_checking = True
    try:
        local  = _get_local_sha()
        remote = _get_remote_sha()
        if local and remote and local != remote:
            _update_available = True
        # if check failed (no remote sha), leave _update_available as-is
    except Exception:
        pass
    _update_checking   = False
    _update_last_check = time.time()

def _maybe_check_update():
    if _update_in_progress or _update_checking:
        return
    if time.time() - _update_last_check < UPDATE_CHECK_INTERVAL:
        return
    threading.Thread(target=_check_update_thread, daemon=True).start()

def _do_update():
    """git pull in background, then restart the service."""
    global _update_in_progress, _update_available

    _update_in_progress = True

    def _pull():
        global _update_in_progress, _update_available
        try:
            subprocess.run(
                ["git", "-C", REPO_PATH, "pull", "--ff-only"],
                capture_output=True, timeout=30
            )
        except Exception:
            pass
        _update_available   = False
        _update_in_progress = False
        subprocess.Popen(["sudo", "systemctl", "restart", "bearbox"])

    threading.Thread(target=_pull, daemon=True).start()

# ── MAIN TEXT ─────────────────────────────────────────────────

def _draw_main(d, F):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    l1_w = tw(LINE1)
    l1_h = th(LINE1)
    l2_h = th(LINE2)

    total_h  = l1_h + LINE_GAP + l2_h
    center_x = int(W * TEXT_X)
    center_y = int(H * TEXT_Y)

    l1_x = center_x - l1_w // 2
    l1_y = center_y - total_h // 2

    if _flicker_active:
        col1 = (0, 60, 120)
    elif _glitch_active:
        col1 = _glitch_color
        l1_x += _glitch_offset[0]
        l1_y += _glitch_offset[1]
        d.text((l1_x + 3, l1_y + 1), LINE1, font=F["main"], fill=(0, 30, 80))
    else:
        col1 = C["white"]

    for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
        d.text((l1_x+ox, l1_y+oy), LINE1, font=F["main"], fill=(0, 20, 50))
    d.text((l1_x, l1_y), LINE1, font=F["main"], fill=col1)

    l2_y = l1_y + l1_h + LINE_GAP

    if _update_available:
        _draw_update_btn(d, F, l2_y)
    else:
        _draw_line2(d, F, l2_y)

def _draw_line2(d, F, y):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    l2_w = tw(LINE2)
    l2_h = th(LINE2)
    l2_x = W // 2 - l2_w // 2

    if _flicker_active:
        col2 = (0, 60, 120)
    elif _glitch_active:
        col2 = _glitch_color
        l2_x += _glitch_offset[0]
        y    += _glitch_offset[1]
        d.text((l2_x - 3, y - 1), LINE2, font=F["main"], fill=(0, 30, 80))
    else:
        col2 = C["blue"]

    for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
        d.text((l2_x+ox, y+oy), LINE2, font=F["main"], fill=(0, 20, 50))
    d.text((l2_x, y), LINE2, font=F["main"], fill=col2)

    line_col = _glitch_color if _glitch_active else C["dimblue"]
    d.line([(l2_x, y + l2_h + 6), (l2_x + l2_w, y + l2_h + 6)],
           fill=line_col, width=2)

def _draw_update_btn(d, F, y):
    """Pulsing update button — sits exactly where LINE2 would be."""
    global _update_btn_rect

    label = "PRESS HERE TO UPDATE" if not _update_in_progress else "UPDATING..."
    sub   = "new version available" if not _update_in_progress else "pulling from github..."

    btn_w = min(W - 40, 340)
    btn_h = 52
    btn_x = (W - btn_w) // 2

    # Pulsing outline — matches hello.py blue palette
    pulse       = (math.sin(time.time() * 3) + 1) / 2
    outline_col = (0, int(100 + pulse * 80), int(200 + pulse * 55))

    # Panel background
    d.rectangle([btn_x, y, btn_x + btn_w, y + btn_h],
                fill=C["panel"], outline=outline_col)

    # Faint horizontal scan stripes inside — same vibe as draw_scanlines
    stripe_col = (0, int(20 + pulse * 10), int(40 + pulse * 25))
    for sy in range(y + 5, y + btn_h - 4, 6):
        d.line([(btn_x + 2, sy), (btn_x + btn_w - 2, sy)],
               fill=stripe_col, width=1)

    # Label — glow + main text
    lw = F["btn"].getbbox(label)[2] - F["btn"].getbbox(label)[0]
    lh = F["btn"].getbbox(label)[3] - F["btn"].getbbox(label)[1]
    lx = btn_x + (btn_w - lw) // 2
    ly = y + (btn_h - lh) // 2

    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        d.text((lx+ox, ly+oy), label, font=F["btn"], fill=(0, 20, 50))

    text_col = outline_col if not _update_in_progress else C["dimwhite"]
    d.text((lx, ly), label, font=F["btn"], fill=text_col)

    # Sub-label — matches CREDIT / underline style
    sw = F["sub"].getbbox(sub)[2] - F["sub"].getbbox(sub)[0]
    sx = (W - sw) // 2
    d.text((sx, y + btn_h + 6), sub, font=F["sub"], fill=C["dimblue"])

    # Underline — same as LINE2 underline in hello.py
    d.line([(btn_x, y + btn_h + 22), (btn_x + btn_w, y + btn_h + 22)],
           fill=C["dimblue"], width=2)

    _update_btn_rect = (btn_x, y, btn_w, btn_h)

def _draw_credit(d, F):
    cw = F["credit"].getbbox(CREDIT)[2]
    ch = F["credit"].getbbox(CREDIT)[3]
    cx = int(W * CREDIT_X) - cw
    cy = int(H * CREDIT_Y) - ch
    d.text((cx, cy), CREDIT, font=F["credit"], fill=C["dimblue"])

# ── MAIN DRAW ─────────────────────────────────────────────────
_tick      = 0
_bg_inited = False

def draw():
    global _tick, _bg_inited
    _tick += 1

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    # Background update check (non-blocking)
    _maybe_check_update()

    # Handle tap on update button
    if _update_available and not _update_in_progress:
        if check_tap() and _update_btn_rect:
            if tapped(*_update_btn_rect):
                _do_update()

    _update_bg()
    _update_glitch()

    img, d = new_frame()
    draw_scanlines(d)
    _draw_bg(d, F)

    if _glitch_active and random.random() < 0.4:
        for _ in range(random.randint(1, 3)):
            gy   = random.randint(0, H)
            gx   = random.randint(0, W // 2)
            gw   = random.randint(20, 100)
            gcol = (0, random.randint(20, 80), random.randint(80, 180))
            d.line([(gx, gy), (gx + gw, gy)], fill=gcol, width=1)

    _draw_main(d, F)
    _draw_credit(d, F)

    push(img)

# ── STANDALONE ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running HELLO LOSER — Ctrl+C to stop")
    _update_last_check = 0   # force immediate check
    while True:
        draw()
        time.sleep(1/30)