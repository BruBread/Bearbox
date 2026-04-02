#!/usr/bin/env python3
"""
BearBox Idle — Update Checker Screen

Replaces the old "NO MODULES DETECTED" screen.
Uses git fetch to compare local HEAD vs origin/main
instead of the GitHub API — faster and always accurate.

States:
  - idle      : before first check
  - checking  : git fetch + compare running
  - uptodate  : local == remote
  - available : update exists, tap button to pull
  - updating  : git pull running, will restart after
"""

import time
import os
import sys
import math
import random
import string
import subprocess
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import check_tap, tapped

# ── Config ────────────────────────────────────────────────────
BRANCH    = "main"
REPO_PATH = "/home/bearbox/bearbox"

# ── Palette ───────────────────────────────────────────────────
U = {
    "bg":      C["bg"],
    "blue":    C["blue"],
    "midblue": C["midblue"],
    "dimblue": C["dimblue"],
    "white":   C["white"],
    "dimwhite":C["dimwhite"],
    "green":   C["green"],
    "dimgreen":C["dimgreen"],
    "amber":   C["amber"],
    "red":     C["red"],
    "panel":   C["panel"],
    "dim":     C["dim"],
}

# ── Fonts ─────────────────────────────────────────────────────
_F = {}

def _fonts():
    if not _F:
        _F["title"]  = font(28, bold=True)
        _F["big"]    = font(22, bold=True)
        _F["body"]   = font(16, bold=True)
        _F["small"]  = font(13)
        _F["tiny"]   = font(11)
        _F["hash"]   = font(13)
        _F["btn"]    = font(18, bold=True)
        _F["credit"] = font(14, bold=True)
    return _F

# ── Background rain ───────────────────────────────────────────
_BG_CHARS    = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")
_BG_COLS     = []
BG_COL_COUNT = 14

def _init_bg(F):
    global _BG_COLS
    col_w = W // BG_COL_COUNT
    _BG_COLS = []
    for i in range(BG_COL_COUNT):
        x = i * col_w + col_w // 2
        _BG_COLS.append({"x": x, "chars": [{
            "char":  random.choice(_BG_CHARS),
            "y":     random.randint(-H, 0) - j * 12,
            "alpha": random.randint(10, 40),
            "speed": random.uniform(0.3, 0.9),
        } for j in range(random.randint(4, 10))]})

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
                d.text((col["x"], int(c["y"])),
                       c["char"], font=F["tiny"],
                       fill=(0, a, int(a * 1.5)))

# ── Update state ──────────────────────────────────────────────
_state           = "idle"
_local_sha       = None
_remote_sha      = None
_check_requested = True    # check immediately on first draw
_update_btn_rect = None
_status_msg      = ""

def request_update_check():
    """Called from idle_main when switching to this screen."""
    global _check_requested
    _check_requested = True

def _run(cmd, timeout=10):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def _check_thread():
    global _state, _local_sha, _remote_sha, _status_msg
    _state = "checking"
    try:
        # fetch latest refs from origin — no merge, just updates remote tracking
        subprocess.run(
            ["git", "-C", REPO_PATH, "fetch", "origin", BRANCH],
            capture_output=True, timeout=15
        )
        # local HEAD
        local  = _run(["git", "-C", REPO_PATH, "rev-parse", "HEAD"])
        # remote HEAD after fetch
        remote = _run(["git", "-C", REPO_PATH, "rev-parse", f"origin/{BRANCH}"])

        _local_sha  = local
        _remote_sha = remote

        print(f"[update] local={local[:8] if local else 'none'} "
              f"remote={remote[:8] if remote else 'none'}")

        if not local or not remote:
            _status_msg = "git error — check repo"
            _state = "idle"
        elif local != remote:
            _status_msg = ""
            _state = "available"
        else:
            _status_msg = ""
            _state = "uptodate"

    except subprocess.TimeoutExpired:
        _status_msg = "fetch timed out"
        _state = "idle"
        print("[update] fetch timed out")
    except Exception as e:
        _status_msg = "check failed"
        _state = "idle"
        print(f"[update] check error: {e}")

def _do_update():
    global _state
    _state = "updating"

    def _pull():
        global _state
        try:
            subprocess.run(
                ["git", "-C", REPO_PATH, "pull", "--ff-only"],
                capture_output=True, timeout=30
            )
        except Exception as e:
            print(f"[update] pull error: {e}")
        _state = "idle"
        subprocess.Popen(["sudo", "systemctl", "restart", "bearbox"])

    threading.Thread(target=_pull, daemon=True).start()

def _maybe_check():
    global _check_requested
    if _state in ("checking", "updating"):
        return
    if not _check_requested:
        return
    _check_requested = False
    threading.Thread(target=_check_thread, daemon=True).start()

# ── Drawing ───────────────────────────────────────────────────

def _draw_header(d, F):
    d.rectangle([0, 0, W, 40], fill=U["panel"])
    d.line([(0, 40), (W, 40)], fill=U["dimblue"], width=1)
    title = "BEARBOX UPDATE"
    tw    = F["title"].getbbox(title)[2]
    d.text(((W - tw) // 2, 6), title, font=F["title"], fill=U["blue"])

def _draw_footer(d, F):
    d.rectangle([0, H - 22, W, H], fill=U["panel"])
    if _state not in ("checking", "updating"):
        hint = "tap anywhere to re-check"
        hw   = F["tiny"].getbbox(hint)[2]
        d.text(((W - hw) // 2, H - 14), hint, font=F["tiny"], fill=U["dimblue"])

def _draw_hash_row(d, F, y, label, sha, color):
    d.text((24, y), label, font=F["small"], fill=U["dimwhite"])
    short = sha[:12] if sha else "unknown"
    hw    = F["hash"].getbbox(short)[2]
    d.text((W - 24 - hw, y), short, font=F["hash"], fill=color)

def _draw_state_checking(d, F):
    spin = ["◐", "◓", "◑", "◒"][int(time.time() * 4) % 4]
    sw   = F["big"].getbbox(spin)[2]
    d.text(((W - sw) // 2, 90), spin, font=F["big"], fill=U["blue"])
    msg  = "fetching from github..."
    mw   = F["body"].getbbox(msg)[2]
    d.text(((W - mw) // 2, 128), msg, font=F["body"], fill=U["dimwhite"])
    sub  = "comparing commits"
    sw2  = F["small"].getbbox(sub)[2]
    d.text(((W - sw2) // 2, 158), sub, font=F["small"], fill=U["dimblue"])
    if _local_sha:
        _draw_hash_row(d, F, 210, "local", _local_sha, U["dimwhite"])

def _draw_state_uptodate(d, F):
    msg = "UP TO DATE"
    mw  = F["big"].getbbox(msg)[2]
    d.text(((W - mw) // 2, 80), msg, font=F["big"], fill=U["green"])
    sub = "no updates available"
    sw  = F["small"].getbbox(sub)[2]
    d.text(((W - sw) // 2, 116), sub, font=F["small"], fill=U["dimgreen"])
    d.line([(40, 148), (W - 40, 148)], fill=U["dimblue"], width=1)
    if _local_sha:
        _draw_hash_row(d, F, 162, "current", _local_sha, U["green"])
    if _remote_sha:
        _draw_hash_row(d, F, 186, "remote",  _remote_sha, U["dimwhite"])
    credit = "-FD"
    cw = F["credit"].getbbox(credit)[2]
    d.text((W - cw - 10, H - 32), credit, font=F["credit"], fill=U["dimblue"])

def _draw_state_available(d, F, pulse):
    global _update_btn_rect

    msg = "UPDATE AVAILABLE"
    mw  = F["big"].getbbox(msg)[2]
    col = (0, int(160 + pulse * 95), int(220 + pulse * 35))
    d.text(((W - mw) // 2, 52), msg, font=F["big"], fill=col)

    if _local_sha:
        _draw_hash_row(d, F, 90,  "installed", _local_sha,  U["dimwhite"])
    if _remote_sha:
        _draw_hash_row(d, F, 112, "available", _remote_sha, U["blue"])

    d.line([(40, 138), (W - 40, 138)], fill=U["dimblue"], width=1)

    btn_w   = W - 48
    btn_h   = 52
    btn_x   = 24
    btn_y   = 150
    outline = (0, int(100 + pulse * 80), int(180 + pulse * 75))
    d.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
                fill=U["panel"], outline=outline)
    for sy in range(btn_y + 6, btn_y + btn_h - 4, 6):
        d.line([(btn_x + 2, sy), (btn_x + btn_w - 2, sy)],
               fill=(0, int(15 + pulse * 12), int(30 + pulse * 20)), width=1)

    label = "TAP TO UPDATE"
    lw    = F["btn"].getbbox(label)[2]
    lh    = F["btn"].getbbox(label)[3]
    lx    = btn_x + (btn_w - lw) // 2
    ly    = btn_y + (btn_h - lh) // 2
    for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        d.text((lx + ox, ly + oy), label, font=F["btn"], fill=(0, 20, 50))
    d.text((lx, ly), label, font=F["btn"], fill=outline)

    _update_btn_rect = (btn_x, btn_y, btn_w, btn_h)

def _draw_state_updating(d, F, pulse):
    spin = ["◐", "◓", "◑", "◒"][int(time.time() * 4) % 4]
    sw   = F["big"].getbbox(spin)[2]
    d.text(((W - sw) // 2, 90),  spin,               font=F["big"],   fill=U["amber"])
    msg  = "UPDATING..."
    mw   = F["body"].getbbox(msg)[2]
    d.text(((W - mw) // 2, 130), msg,                font=F["body"],  fill=U["amber"])
    sub  = "pulling from github"
    sw2  = F["small"].getbbox(sub)[2]
    d.text(((W - sw2) // 2, 158), sub,               font=F["small"], fill=U["dimwhite"])
    sub2 = "will restart automatically"
    sw3  = F["small"].getbbox(sub2)[2]
    d.text(((W - sw3) // 2, 178), sub2,              font=F["small"], fill=U["dimwhite"])

def _draw_state_idle(d, F):
    msg = "tap to check for updates"
    mw  = F["body"].getbbox(msg)[2]
    d.text(((W - mw) // 2, H // 2 - 10), msg,
           font=F["body"], fill=U["dimwhite"])
    if _status_msg:
        sw = F["small"].getbbox(_status_msg)[2]
        d.text(((W - sw) // 2, H // 2 + 20), _status_msg,
               font=F["small"], fill=U["red"])

# ── Main draw ─────────────────────────────────────────────────
_tick      = 0
_bg_inited = False

def draw():
    global _tick, _bg_inited
    _tick += 1

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    _maybe_check()

    pulse = (math.sin(time.time() * 3) + 1) / 2

    if _state not in ("checking", "updating"):
        if check_tap():
            if _state == "available" and _update_btn_rect and tapped(*_update_btn_rect):
                _do_update()
            else:
                request_update_check()

    _update_bg()

    img, d = new_frame(bg=U["bg"])
    draw_scanlines(d)
    _draw_bg(d, F)
    _draw_header(d, F)

    if _state == "checking":
        _draw_state_checking(d, F)
    elif _state == "uptodate":
        _draw_state_uptodate(d, F)
    elif _state == "available":
        _draw_state_available(d, F, pulse)
    elif _state == "updating":
        _draw_state_updating(d, F, pulse)
    else:
        _draw_state_idle(d, F)

    _draw_footer(d, F)
    push(img)

# ── Standalone ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Update screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1 / 30)