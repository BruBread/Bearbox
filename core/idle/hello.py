#!/usr/bin/env python3
"""
BearBox Idle — Update Checker Screen

States:
  checking  — git fetch running in background
  uptodate  — local == remote, show confirmation + "CHECK AGAIN" button
  available — update exists, show "TAP TO UPDATE" button
  updating  — git pull running, will restart only if pull succeeds
"""

import time, os, sys, math, random, string, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_scanlines, font, C, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap, tapped

# Reset _last_tap so boot residue doesn't trigger a phantom tap on first draw
_net_utils._last_tap = time.time()

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
        _F["btn"]    = font(18, bold=True)
    return _F

# ── Background rain ───────────────────────────────────────────
_BG_CHARS    = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")
_BG_COLS     = []

def _init_bg(F):
    global _BG_COLS
    col_w = W // 14
    _BG_COLS = []
    for i in range(14):
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
                d.text((col["x"], int(c["y"])), c["char"],
                       font=F["tiny"], fill=(0, a, int(a * 1.5)))

# ── State ─────────────────────────────────────────────────────
_state       = "checking"   # start checking immediately
_local_sha   = None
_remote_sha  = None
_status_msg  = ""
_btn_rect    = None         # set during draw, read during tap check
_btn_pressed = 0.0          # timestamp until button shows pressed flash
_bg_inited   = False

def _git(args, timeout=15):
    cmd = ["sudo", "-u", "bearbox", "git", "-C", REPO_PATH] + args
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "HOME": "/home/bearbox"}
    r   = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=timeout, env=env)
    print(f"[hello] git {' '.join(args)} rc={r.returncode}")
    if r.returncode != 0:
        print(f"[hello]   stderr: {r.stderr.strip()[:80]}")
    return r.stdout.strip() if r.returncode == 0 else None

def _check_thread():
    global _state, _local_sha, _remote_sha, _status_msg
    try:
        if _git(["rev-parse", "--git-dir"], timeout=5) is None:
            _status_msg = "not a git repo"
            _state = "uptodate"   # show screen, don't loop
            return

        if _git(["fetch", "origin", BRANCH], timeout=20) is None:
            _status_msg = "fetch failed"
            _state = "uptodate"   # show screen, don't loop
            return

        local  = _git(["rev-parse", "HEAD"])
        remote = _git(["rev-parse", f"origin/{BRANCH}"])
        _local_sha  = local
        _remote_sha = remote
        print(f"[hello] local={local[:8] if local else '?'}  remote={remote[:8] if remote else '?'}")

        if local and remote and local != remote:
            _state = "available"
        else:
            _status_msg = ""
            _state = "uptodate"

    except subprocess.TimeoutExpired:
        _status_msg = "fetch timed out"
        _state = "uptodate"
    except Exception as e:
        _status_msg = str(e)[:60]
        _state = "uptodate"

def _start_check():
    global _state
    _state = "checking"
    threading.Thread(target=_check_thread, daemon=True).start()

def _do_update():
    global _state
    _state = "updating"

    def _pull():
        global _state
        try:
            r = subprocess.run(
                ["sudo", "-u", "bearbox", "git", "-C", REPO_PATH,
                 "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "HOME": "/home/bearbox"}
            )
            print(f"[hello] pull rc={r.returncode} {r.stdout.strip()[:60]}")
            if r.returncode == 0 and "Already up to date" not in r.stdout:
                # Actually pulled new code — restart
                subprocess.Popen(["sudo", "systemctl", "restart", "bearbox"])
                return
        except Exception as e:
            print(f"[hello] pull error: {e}")
        # Pull failed or nothing new — go back to uptodate
        _state = "uptodate"

    threading.Thread(target=_pull, daemon=True).start()

# Start the first check immediately at import time
_check_thread_started = False

# ── Drawing ───────────────────────────────────────────────────

def _header(d, F):
    d.rectangle([0, 0, W, 40], fill=C["panel"])
    d.line([(0, 40), (W, 40)], fill=C["dimblue"], width=1)
    t  = "BEARBOX UPDATE"
    tw = F["title"].getbbox(t)[2]
    d.text(((W - tw) // 2, 6), t, font=F["title"], fill=C["blue"])

def _hash_row(d, F, y, label, sha, color):
    d.text((24, y), label, font=F["small"], fill=C["dimwhite"])
    s  = sha[:12] if sha else "?"
    sw = F["small"].getbbox(s)[2]
    d.text((W - 24 - sw, y), s, font=F["small"], fill=color)

def _spinner(d, F, y, color):
    s  = ["◐","◓","◑","◒"][int(time.time() * 4) % 4]
    sw = F["big"].getbbox(s)[2]
    d.text(((W - sw) // 2, y), s, font=F["big"], fill=color)

def _btn(d, F, label, y, pulse):
    global _btn_rect
    bx, bw, bh = 24, W - 48, 52
    pressed     = time.time() < _btn_pressed
    outline     = C["white"] if pressed else (0, int(100+pulse*80), int(180+pulse*75))
    fill        = (20, 60, 100) if pressed else C["panel"]
    d.rectangle([bx, y, bx+bw, y+bh], fill=fill, outline=outline)
    for sy in range(y+6, y+bh-4, 6):
        d.line([(bx+2, sy), (bx+bw-2, sy)],
               fill=(0, int(15+pulse*10), int(30+pulse*20)), width=1)
    lw = F["btn"].getbbox(label)[2]
    lh = F["btn"].getbbox(label)[3]
    lx = bx + (bw - lw) // 2
    ly = y  + (bh - lh) // 2
    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        d.text((lx+ox, ly+oy), label, font=F["btn"], fill=(0,20,50))
    d.text((lx, ly), label, font=F["btn"], fill=outline)
    _btn_rect = (bx, y, bw, bh)

def _draw_checking(d, F):
    _spinner(d, F, 90, C["blue"])
    for txt, y, col in [
        ("fetching from github...", 130, C["dimwhite"]),
        ("comparing commits",       158, C["dimblue"]),
    ]:
        tw = F["body"].getbbox(txt)[2]
        d.text(((W-tw)//2, y), txt, font=F["body"], fill=col)
    if _local_sha:
        _hash_row(d, F, 210, "local", _local_sha, C["dimwhite"])

def _draw_uptodate(d, F, pulse):
    if _status_msg:
        # Error state — show message, offer retry
        msg = "CHECK FAILED"
        mw  = F["big"].getbbox(msg)[2]
        d.text(((W-mw)//2, 60), msg, font=F["big"], fill=C["amber"])
        sw = F["small"].getbbox(_status_msg)[2]
        d.text(((W-sw)//2, 96), _status_msg, font=F["small"], fill=C["dimwhite"])
    else:
        msg = "UP TO DATE"
        mw  = F["big"].getbbox(msg)[2]
        d.text(((W-mw)//2, 60), msg, font=F["big"], fill=C["green"])
        sub = "you're on the latest version"
        sw  = F["small"].getbbox(sub)[2]
        d.text(((W-sw)//2, 94), sub, font=F["small"], fill=C["dimgreen"])
        if _local_sha:
            _hash_row(d, F, 130, "current", _local_sha, C["green"])

    d.line([(40, 155), (W-40, 155)], fill=C["dimblue"], width=1)
    _btn(d, F, "CHECK AGAIN", 165, pulse)

def _draw_available(d, F, pulse):
    msg = "UPDATE AVAILABLE"
    mw  = F["big"].getbbox(msg)[2]
    col = (0, int(160+pulse*95), int(220+pulse*35))
    d.text(((W-mw)//2, 52), msg, font=F["big"], fill=col)
    if _local_sha:  _hash_row(d, F, 90,  "installed", _local_sha,  C["dimwhite"])
    if _remote_sha: _hash_row(d, F, 112, "available", _remote_sha, C["blue"])
    d.line([(40, 138), (W-40, 138)], fill=C["dimblue"], width=1)
    _btn(d, F, "TAP TO UPDATE", 148, pulse)

def _draw_updating(d, F):
    _spinner(d, F, 90, C["amber"])
    for txt, y, fnt, col in [
        ("UPDATING...",              128, F["body"],  C["amber"]),
        ("pulling from github",      158, F["small"], C["dimwhite"]),
        ("will restart if updated",  178, F["small"], C["dimwhite"]),
    ]:
        tw = fnt.getbbox(txt)[2]
        d.text(((W-tw)//2, y), txt, font=fnt, fill=col)

# ── Main draw — called by idle_main 30x/sec ───────────────────
def draw():
    """
    Returns:
      True  — tap outside button, idle_main should cycle screen
      False — tap on button (or busy), idle_main must NOT cycle
    hello always returns True or False, never None, so idle_main
    never calls check_tap() on our behalf.
    """
    global _bg_inited, _check_thread_started, _btn_pressed

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    # Kick off the very first check
    if not _check_thread_started:
        _check_thread_started = True
        _start_check()

    pulse = (math.sin(time.time() * 3) + 1) / 2
    _update_bg()

    # ── Draw ──────────────────────────────────────────────────
    img, d = new_frame(bg=C["bg"])
    draw_scanlines(d)
    _draw_bg(d, F)
    _header(d, F)

    if   _state == "checking":  _draw_checking(d, F)
    elif _state == "available": _draw_available(d, F, pulse)
    elif _state == "updating":  _draw_updating(d, F)
    else:                       _draw_uptodate(d, F, pulse)   # uptodate + errors

    if _state not in ("checking", "updating"):
        hint = "tap outside button to switch screen"
        hw   = F["tiny"].getbbox(hint)[2]
        d.text(((W-hw)//2, H-14), hint, font=F["tiny"], fill=C["dimblue"])

    push(img)

    # ── Tap — always consume so idle_main never sees our events ──
    if _state in ("checking", "updating"):
        check_tap()   # drain only
        return False

    if check_tap():
        tx, ty = _net_utils._tap_x, _net_utils._tap_y
        print(f"[hello] tap ({tx},{ty}) btn={_btn_rect} state={_state}")
        if _btn_rect and tapped(*_btn_rect):
            print("[hello] HIT")
            _btn_pressed = time.time() + 0.35
            if _state == "available":
                _do_update()
            else:
                _start_check()
            return False
        else:
            print("[hello] MISS — cycle")
            return True

    return False

if __name__ == "__main__":
    print("Update screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)