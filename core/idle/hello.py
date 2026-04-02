#!/usr/bin/env python3
"""
BearBox Idle — HELLO / NO MODULES Screensaver
- Giant centered text with glitch/flicker effect
- Hacking terminal noise in background
- Blue and white color scheme

Update check:
  - Runs once when you first land on this screen (called from idle_main)
  - Shows a pulsing "PRESS HERE TO UPDATE" button if a new commit exists
  - Tapping it runs git pull and restarts bearbox
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

LINE1      = "NO MODULES"
LINE2      = "DETECTED"
CREDIT     = "-FD"

MAIN_SIZE   = 90
CREDIT_SIZE = 18
BG_SIZE     = 10

TEXT_X      = 0.5
TEXT_Y      = 0.4
CREDIT_X    = 0.97
CREDIT_Y    = 0.92
LINE_GAP    = 8

GLITCH_CHANCE    = 0.08
GLITCH_INTENSITY = 6
FLICKER_CHANCE   = 0.04

BG_COLS     = 12

REPO_OWNER  = "BruBread"
REPO_NAME   = "Bearbox"       # case-sensitive — match exactly as on GitHub
BRANCH      = "main"
REPO_PATH   = "/home/bearbox/bearbox"



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
_update_available    = False
_update_checking     = False
_update_in_progress  = False
_update_check_requested = True   # check immediately on first load
_update_btn_rect     = None

def request_update_check():
    """Call this from idle_main when switching to this screen."""
    global _update_check_requested
    _update_check_requested = True

def _get_local_sha():
    try:
        r = subprocess.run(
            ["git", "-C", REPO_PATH, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception as e:
        print(f"[hello] local sha error: {e}")
        return None

def _get_remote_sha():
    try:
        url = (f"https://api.github.com/repos/"
               f"{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}")
        r = subprocess.run(
            ["curl", "-sf", "--max-time", "8",
             "-H", "Accept: application/vnd.github.v3+json",
             url],
            capture_output=True, text=True, timeout=12
        )
        if not r.stdout.strip():
            print(f"[hello] GitHub API empty response")
            return None
        data = json.loads(r.stdout)
        sha  = data.get("sha", "")
        print(f"[hello] remote sha: {sha[:10]}...")
        return sha
    except Exception as e:
        print(f"[hello] remote sha error: {e}")
        return None

def _check_update_thread():
    global _update_available, _update_checking
    _update_checking = True
    try:
        local  = _get_local_sha()
        remote = _get_remote_sha()
        print(f"[hello] local={local[:10] if local else None} remote={remote[:10] if remote else None}")
        if local and remote and local != remote:
            _update_available = True
            print("[hello] Update available!")
        else:
            _update_available = False
            print("[hello] Up to date")
    except Exception as e:
        print(f"[hello] update check error: {e}")
    _update_checking = False

def _maybe_check_update():
    global _update_check_requested
    if _update_in_progress or _update_checking:
        return
    if not _update_check_requested:
        return
    _update_check_requested = False
    print("[hello] Checking for updates...")
    threading.Thread(target=_check_update_thread, daemon=True).start()

def _do_update():
    global _update_in_progress, _update_available

    _update_in_progress = True

    def _pull():
        global _update_in_progress, _update_available
        try:
            subprocess.run(
                ["git", "-C", REPO_PATH, "pull", "--ff-only"],
                capture_output=True, timeout=30
            )
        except Exception as e:
            print(f"[hello] pull error: {e}")
        _update_available   = False
        _update_in_progress = False
        subprocess.Popen(["sudo", "systemctl", "restart", "bearbox"])

    threading.Thread(target=_pull, daemon=True).start()

# ── MAIN TEXT ─────────────────────────────────────────────────

def _draw_main(d, F):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    l1_w    = tw(LINE1)
    l1_h    = th(LINE1)
    l2_h    = th(LINE2)
    total_h = l1_h + LINE_GAP + l2_h

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
    elif _update_checking:
        _draw_checking(d, F, l2_y)
    else:
        _draw_line2(d, F, l2_y)

def _draw_checking(d, F, y):
    """Small 'checking...' indicator while update check is in progress."""
    dots = "." * (int(time.time() * 2) % 4)
    msg  = f"checking{dots}"
    mw   = F["sub"].getbbox(msg)[2]
    d.text(((W - mw) // 2, y + 10), msg, font=F["sub"], fill=C["dimblue"])

def _draw_line2(d, F, y):
    def tw(t): return F["main"].getbbox(t)[2] - F["main"].getbbox(t)[0]
    def th(t): return F["main"].getbbox(t)[3] - F["main"].getbbox(t)[1]

    l2_w = tw(LINE2)
    l2_h = th(LINE2)
    l2_x = W // 2 - l2_w // 2

    if _flicker_active:
        col2 = (0, 60, 120)
    elif _glitch_active:
        col2  = _glitch_color
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
    global _update_btn_rect

    label = "PRESS HERE TO UPDATE" if not _update_in_progress else "UPDATING..."
    sub   = "new version available" if not _update_in_progress else "pulling from github..."

    btn_w = min(W - 40, 340)
    btn_h = 52
    btn_x = (W - btn_w) // 2

    pulse       = (math.sin(time.time() * 3) + 1) / 2
    outline_col = (0, int(100 + pulse * 80), int(200 + pulse * 55))

    d.rectangle([btn_x, y, btn_x + btn_w, y + btn_h],
                fill=C["panel"], outline=outline_col)

    stripe_col = (0, int(20 + pulse * 10), int(40 + pulse * 25))
    for sy in range(y + 5, y + btn_h - 4, 6):
        d.line([(btn_x + 2, sy), (btn_x + btn_w - 2, sy)],
               fill=stripe_col, width=1)

    lw = F["btn"].getbbox(label)[2] - F["btn"].getbbox(label)[0]
    lh = F["btn"].getbbox(label)[3] - F["btn"].getbbox(label)[1]
    lx = btn_x + (btn_w - lw) // 2
    ly = y + (btn_h - lh) // 2

    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        d.text((lx+ox, ly+oy), label, font=F["btn"], fill=(0, 20, 50))

    text_col = outline_col if not _update_in_progress else C["dimwhite"]
    d.text((lx, ly), label, font=F["btn"], fill=text_col)

    sw = F["sub"].getbbox(sub)[2] - F["sub"].getbbox(sub)[0]
    sx = (W - sw) // 2
    d.text((sx, y + btn_h + 6), sub, font=F["sub"], fill=C["dimblue"])

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

    _maybe_check_update()

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
    print("Running HELLO — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)