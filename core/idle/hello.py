#!/usr/bin/env python3
"""
BearBox Idle — Update Checker Screen

States:
  - idle      : before first check / error
  - checking  : git fetch + compare running
  - uptodate  : local == remote
  - available : update exists, tap button to pull
  - updating  : git pull running, will restart after

Tap the CHECK / TAP TO UPDATE button → action.
Tap anywhere else → cycle to next screen (handled by idle_main).
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
_update_btn_rect = None    # (x, y, w, h) of action button — set each frame
_status_msg      = ""

# Return value from draw() — None means stay, True means "cycle to next screen"
_cycle_requested = False

def request_update_check():
    global _check_requested
    _check_requested = True

def _run(cmd, timeout=10):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip() if r.returncode == 0 else None

def _check_thread():
    global _state, _local_sha, _remote_sha, _status_msg
    _state = "checking"
    try:
        # ── verify repo exists ────────────────────────────────
        if not os.path.isdir(REPO_PATH):
            _status_msg = f"repo not found: {REPO_PATH}"
            _state = "idle"
            return

        # ── find .git — handle both normal repo and worktrees ─
        git_dir = None
        for candidate in [
            os.path.join(REPO_PATH, ".git"),
            REPO_PATH,                          # bare repo
        ]:
            r = subprocess.run(
                ["git", "-C", REPO_PATH, "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                git_dir = r.stdout.strip()
                break

        if git_dir is None:
            # Last-ditch: maybe service runs as root, try with sudo
            r = subprocess.run(
                ["sudo", "-u", "bearbox", "git", "-C", REPO_PATH,
                 "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                _status_msg = "not a git repo — run install.sh"
                _state = "idle"
                return

        # ── fetch ─────────────────────────────────────────────
        fetch = subprocess.run(
            ["git", "-C", REPO_PATH, "fetch", "origin", BRANCH],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        if fetch.returncode != 0:
            _status_msg = "fetch failed — check network"
            _state = "idle"
            return

        local  = _run(["git", "-C", REPO_PATH, "rev-parse", "HEAD"])
        remote = _run(["git", "-C", REPO_PATH, "rev-parse", f"origin/{BRANCH}"])

        _local_sha  = local
        _remote_sha = remote

        if not local or not remote:
            _status_msg = "git error — check logs"
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
    except Exception as e:
        _status_msg = str(e)[:40]
        _state = "idle"

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

# ── Drawing helpers ───────────────────────────────────────────

def _draw_header(d, F):
    d.rectangle([0, 0, W, 40], fill=C["panel"])
    d.line([(0, 40), (W, 40)], fill=C["dimblue"], width=1)
    title = "BEARBOX UPDATE"
    tw    = F["title"].getbbox(title)[2]
    d.text(((W - tw) // 2, 6), title, font=F["title"], fill=C["blue"])

def _draw_hash_row(d, F, y, label, sha, color):
    d.text((24, y), label, font=F["small"], fill=C["dimwhite"])
    short = sha[:12] if sha else "unknown"
    hw    = F["hash"].getbbox(short)[2]
    d.text((W - 24 - hw, y), short, font=F["hash"], fill=color)

def _draw_action_btn(d, F, label, pulse, y=None):
    """Draw the main action button and store its rect. Returns (x,y,w,h)."""
    global _update_btn_rect
    btn_w = W - 48
    btn_h = 52
    btn_x = 24
    btn_y = y if y is not None else H - btn_h - 28
    outline = (0, int(100 + pulse * 80), int(180 + pulse * 75))
    d.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
                fill=C["panel"], outline=outline)
    for sy in range(btn_y + 6, btn_y + btn_h - 4, 6):
        d.line([(btn_x + 2, sy), (btn_x + btn_w - 2, sy)],
               fill=(0, int(15 + pulse * 12), int(30 + pulse * 20)), width=1)
    lw = F["btn"].getbbox(label)[2]
    lh = F["btn"].getbbox(label)[3]
    lx = btn_x + (btn_w - lw) // 2
    ly = btn_y + (btn_h - lh) // 2
    for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        d.text((lx + ox, ly + oy), label, font=F["btn"], fill=(0, 20, 50))
    d.text((lx, ly), label, font=F["btn"], fill=outline)
    _update_btn_rect = (btn_x, btn_y, btn_w, btn_h)
    return _update_btn_rect

def _draw_spinner(d, F, y, color):
    spin = ["◐", "◓", "◑", "◒"][int(time.time() * 4) % 4]
    sw   = F["big"].getbbox(spin)[2]
    d.text(((W - sw) // 2, y), spin, font=F["big"], fill=color)

# ── State renderers ───────────────────────────────────────────

def _draw_checking(d, F):
    _draw_spinner(d, F, 90, C["blue"])
    for txt, y, col in [
        ("fetching from github...", 130, C["dimwhite"]),
        ("comparing commits",       158, C["dimblue"]),
    ]:
        tw = F["body"].getbbox(txt)[2]
        d.text(((W - tw) // 2, y), txt, font=F["body"], fill=col)
    if _local_sha:
        _draw_hash_row(d, F, 210, "local", _local_sha, C["dimwhite"])

def _draw_uptodate(d, F, pulse):
    msg = "UP TO DATE"
    mw  = F["big"].getbbox(msg)[2]
    d.text(((W - mw) // 2, 60), msg, font=F["big"], fill=C["green"])
    sub = "you're on the latest version"
    sw  = F["small"].getbbox(sub)[2]
    d.text(((W - sw) // 2, 94), sub, font=F["small"], fill=C["dimgreen"])
    d.line([(40, 122), (W - 40, 122)], fill=C["dimblue"], width=1)
    if _local_sha:
        _draw_hash_row(d, F, 136, "current", _local_sha, C["green"])
    if _remote_sha:
        _draw_hash_row(d, F, 158, "remote",  _remote_sha, C["dimwhite"])
    # re-check button at bottom
    _draw_action_btn(d, F, "CHECK AGAIN", pulse)

def _draw_available(d, F, pulse):
    msg = "UPDATE AVAILABLE"
    mw  = F["big"].getbbox(msg)[2]
    col = (0, int(160 + pulse * 95), int(220 + pulse * 35))
    d.text(((W - mw) // 2, 50), msg, font=F["big"], fill=col)
    if _local_sha:
        _draw_hash_row(d, F, 88,  "installed", _local_sha,  C["dimwhite"])
    if _remote_sha:
        _draw_hash_row(d, F, 110, "available", _remote_sha, C["blue"])
    d.line([(40, 136), (W - 40, 136)], fill=C["dimblue"], width=1)
    _draw_action_btn(d, F, "TAP TO UPDATE", pulse, y=148)

def _draw_updating(d, F):
    _draw_spinner(d, F, 90, C["amber"])
    for txt, y, col in [
        ("UPDATING...",             130, C["amber"]),
        ("pulling from github",     158, C["dimwhite"]),
        ("will restart automatically", 178, C["dimwhite"]),
    ]:
        tw = F["body"].getbbox(txt)[2] if col == C["amber"] else F["small"].getbbox(txt)[2]
        fnt = F["body"] if col == C["amber"] else F["small"]
        d.text(((W - tw) // 2, y), txt, font=fnt, fill=col)

def _draw_idle(d, F, pulse):
    msg = "tap to check for updates"
    mw  = F["body"].getbbox(msg)[2]
    d.text(((W - mw) // 2, 80), msg, font=F["body"], fill=C["dimwhite"])
    if _status_msg:
        sw = F["small"].getbbox(_status_msg)[2]
        d.text(((W - sw) // 2, 112), _status_msg,
               font=F["small"], fill=C.get("red", (220, 60, 60)))
    # always show a check button so there's a specific tap target
    _draw_action_btn(d, F, "CHECK FOR UPDATES", pulse)

# ── Main draw ─────────────────────────────────────────────────
_bg_inited = False

def draw():
    """
    Returns True if the caller (idle_main) should cycle to the next screen.
    Returns None/False to stay on this screen.
    """
    global _bg_inited, _cycle_requested

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    _maybe_check()

    pulse = (math.sin(time.time() * 3) + 1) / 2

    # ── Touch handling ────────────────────────────────────────
    # Return contract for idle_main:
    #   True  = tapped outside button → cycle to next screen
    #   False = tapped button → action taken, do NOT cycle
    #   None  = no tap this frame
    tap_result = None
    if _state not in ("checking", "updating"):
        if check_tap():
            if _update_btn_rect and tapped(*_update_btn_rect):
                # Button tap — do the action, suppress cycling
                if _state == "available":
                    _do_update()
                else:
                    request_update_check()
                tap_result = False
            else:
                # Outside tap — cycle
                tap_result = True

    _update_bg()

    img, d = new_frame(bg=C["bg"])
    draw_scanlines(d)
    _draw_bg(d, F)
    _draw_header(d, F)

    if   _state == "checking":  _draw_checking(d, F)
    elif _state == "uptodate":  _draw_uptodate(d, F, pulse)
    elif _state == "available": _draw_available(d, F, pulse)
    elif _state == "updating":  _draw_updating(d, F)
    else:                       _draw_idle(d, F, pulse)

    # Footer hint
    if _state not in ("checking", "updating"):
        hint = "tap outside button to switch screen"
        hw   = F["tiny"].getbbox(hint)[2]
        d.text(((W - hw) // 2, H - 14), hint,
               font=F["tiny"], fill=C["dimblue"])

    push(img)
    return tap_result

# ── Standalone ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Update screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1 / 30)