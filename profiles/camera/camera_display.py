#!/usr/bin/env python3
"""
BearBox Camera — LCD Display

Two screens, tap to cycle:
  0 — SURVEILLANCE ACTIVE  (status + stream URL + AI caption status)
  1 — INFO page            (FPS, motion count, last motion, IP)

Reads from DetectionState — no camera access here.
"""

import os
import sys
import time
import select
import struct
import subprocess

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, draw_corner_brackets, C, W, H

# Amber palette consistent with camera connected screen
A = {
    "bg":       (0,    5,   15),
    "amber":    (255, 176,   0),
    "dimamber": (120,  70,   0),
    "darkamber":(20,   10,   0),
    "panel":    (5,    15,  30),
    "white":    (240, 248, 255),
    "dimwhite": (100, 120, 145),
    "red":      (255,  50,  50),
    "dimred":   (120,  20,  20),
    "green":    (0,   255,  80),
    "dimgreen": (0,    80,  35),
}

# Caption status → (display text, color)
_CAPTION_STYLE = {
    "IDLE":            ("IDLE",              A["dimamber"]),
    "MOTION DETECTED": ("MOTION DETECTED",   A["red"]),
    "LOADING MODEL...":("LOADING MODEL...",  A["amber"]),
    "PROCESSING...":   ("PROCESSING...",     A["amber"]),
    "COOLDOWN":        ("COOLDOWN",          A["dimwhite"]),
    "ERROR":           ("AI ERROR",          A["red"]),
}

# ── Touch — 64/32-bit safe ────────────────────────────────────
TOUCH_DEV    = "/dev/input/event0"
TAP_COOLDOWN = 1.0

_FMT_64  = "llHHi"
_FMT_32  = "iIHHi"
_SZ_64   = struct.calcsize(_FMT_64)
_SZ_32   = struct.calcsize(_FMT_32)

_touch_fd = None
_last_tap = 0
_evt_size = _SZ_64
_evt_fmt  = _FMT_64

def _check_tap():
    global _touch_fd, _last_tap, _evt_size, _evt_fmt
    if not os.path.exists(TOUCH_DEV):
        return False
    try:
        if _touch_fd is None:
            _touch_fd = open(TOUCH_DEV, "rb")
        r, _, _ = select.select([_touch_fd], [], [], 0)
        if r:
            while True:
                r2, _, _ = select.select([_touch_fd], [], [], 0)
                if not r2:
                    break
                data = _touch_fd.read(_evt_size)
                if not data:
                    break
                if len(data) == _SZ_32 and _evt_fmt == _FMT_64:
                    _evt_fmt  = _FMT_32
                    _evt_size = _SZ_32
                if len(data) == _evt_size:
                    try:
                        _, _, etype, ecode, evalue = struct.unpack(_evt_fmt, data)
                    except struct.error:
                        pass
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except Exception:
        _touch_fd = None
    return False

# ── Helpers ───────────────────────────────────────────────────

def _get_ip():
    try:
        out = subprocess.run(
            "hostname -I", shell=True, capture_output=True, text=True
        ).stdout.strip()
        return out.split()[0] if out else "unknown"
    except Exception:
        return "unknown"

def _fmt_time(ts):
    if ts is None:
        return "never"
    elapsed = time.time() - ts
    if elapsed < 60:
        return f"{int(elapsed)}s ago"
    elif elapsed < 3600:
        return f"{int(elapsed // 60)}m ago"
    else:
        return f"{int(elapsed // 3600)}h ago"

# ── Screen 0 — SURVEILLANCE ACTIVE ───────────────────────────

def _draw_surveillance(state, pulse, ip, port):
    status    = state.get_status()
    motion    = status["motion"]
    cap_stat  = status.get("caption_status", "IDLE")

    F_big  = font(52, bold=True)
    F_med  = font(18, bold=True)
    F_small= font(13)
    F_tiny = font(11)

    img, d = new_frame(bg=A["bg"])

    # scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    # corner brackets — amber normally, red when motion
    bracket_col = A["red"] if motion else A["amber"]
    draw_corner_brackets(d, bracket_col, size=18, thickness=2)

    # pulsing motion indicator dot
    dot_amp = abs((pulse % 30) - 15) / 15.0
    dot_col = (int(200 + dot_amp * 55), 30, 30) if motion else A["dimamber"]
    d.ellipse([W // 2 - 6, 18, W // 2 + 6, 30], fill=dot_col)

    # main text
    label = "SURVEILLANCE"
    lw    = F_big.getbbox(label)[2]
    d.text(((W - lw) // 2, 38), label, font=F_big, fill=A["amber"])

    label2 = "ACTIVE" if not motion else "MOTION!"
    col2   = A["dimwhite"] if not motion else A["red"]
    lw2    = F_med.getbbox(label2)[2]
    d.text(((W - lw2) // 2, 96), label2, font=F_med, fill=col2)

    # divider
    d.line([(30, 122), (W - 30, 122)], fill=A["dimamber"], width=1)

    # ── AI caption status row ─────────────────────────────────
    cap_text, cap_col = _CAPTION_STYLE.get(
        cap_stat, (cap_stat, A["dimwhite"])
    )

    # pulsing amber dot when processing
    if cap_stat in ("PROCESSING...", "LOADING MODEL..."):
        pulse_frac = abs((pulse % 20) - 10) / 10.0
        dot_c = (
            int(120 + pulse_frac * 135),
            int(50  + pulse_frac * 126),
            0,
        )
    else:
        dot_c = cap_col

    ai_label = "AI"
    ai_lw    = F_tiny.getbbox(ai_label)[2]
    cap_lw   = F_tiny.getbbox(cap_text)[2]
    row_y    = 130

    d.text((30, row_y), ai_label, font=F_tiny, fill=A["dimamber"])
    # small indicator dot
    d.ellipse([30 + ai_lw + 6, row_y + 3,
               30 + ai_lw + 12, row_y + 9], fill=dot_c)
    d.text((30 + ai_lw + 18, row_y), cap_text, font=F_tiny, fill=cap_col)

    # divider
    d.line([(30, 148), (W - 30, 148)], fill=A["darkamber"], width=1)

    # stream URL
    url  = f"http://{ip}:{port}/stream"
    uw   = F_small.getbbox(url)[2]
    d.text(((W - uw) // 2, 156), url, font=F_small, fill=A["dimwhite"])

    hint = "open in browser to view"
    hw   = F_tiny.getbbox(hint)[2]
    d.text(((W - hw) // 2, 174), hint, font=F_tiny, fill=A["dimamber"])

    # log URL hint
    log_hint = f"log: :{port}/log/ui"
    lhw      = F_tiny.getbbox(log_hint)[2]
    d.text(((W - lhw) // 2, 190), log_hint, font=F_tiny, fill=A["dimamber"])

    # footer hint
    d.rectangle([0, H - 24, W, H], fill=A["panel"])
    foot = "tap for info"
    fw   = F_tiny.getbbox(foot)[2]
    d.text(((W - fw) // 2, H - 16), foot, font=F_tiny, fill=A["dimamber"])

    push(img)

# ── Screen 1 — INFO ───────────────────────────────────────────

def _draw_info(state, ip, port):
    status = state.get_status()
    F_hdr  = font(16, bold=True)
    F_lbl  = font(13)
    F_val  = font(15, bold=True)
    F_tiny = font(11)

    img, d = new_frame(bg=A["bg"])
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    # header bar
    d.rectangle([0, 0, W, 38], fill=A["panel"])
    d.line([(0, 38), (W, 38)], fill=A["dimamber"], width=1)
    title = "CAMERA INFO"
    tw    = F_hdr.getbbox(title)[2]
    d.text(((W - tw) // 2, 10), title, font=F_hdr, fill=A["amber"])

    # caption status — truncate if too long for the value column
    cap_stat = status.get("caption_status", "IDLE")
    cap_col  = _CAPTION_STYLE.get(cap_stat, (cap_stat, A["dimwhite"]))[1]

    # rows
    rows = [
        ("FPS",          f"{status['fps']:.1f}",
         A["white"]),
        ("MOTION EVENTS",str(status["motion_count"]),
         A["red"] if status["motion_count"] > 0 else A["dimwhite"]),
        ("LAST MOTION",  _fmt_time(status["last_motion"]),
         A["dimwhite"]),
        ("STATUS",       "MOTION" if status["motion"] else "CLEAR",
         A["red"] if status["motion"] else A["green"]),
        ("AI",           cap_stat[:12],   # truncate to fit
         cap_col),
        ("STREAM",       f":{port}/stream",
         A["dimamber"]),
        ("IP",           ip,
         A["dimwhite"]),
    ]

    y_start = 50
    row_h   = 34
    pad_x   = 20

    for i, (label, value, val_col) in enumerate(rows):
        y = y_start + i * row_h
        if i > 0:
            d.line([(pad_x, y - 2), (W - pad_x, y - 2)],
                   fill=A["darkamber"], width=1)
        vw = F_val.getbbox(value)[2]
        d.text((pad_x,          y + 6), label, font=F_lbl, fill=A["dimamber"])
        d.text((W - pad_x - vw, y + 5), value, font=F_val, fill=val_col)

    # footer
    d.rectangle([0, H - 24, W, H], fill=A["panel"])
    foot = "tap to go back"
    fw   = F_tiny.getbbox(foot)[2]
    d.text(((W - fw) // 2, H - 16), foot, font=F_tiny, fill=A["dimamber"])

    push(img)

# ── Main display loop ─────────────────────────────────────────

def run_display(state, port=5000):
    """
    Runs the LCD display loop.
    Call in the main thread from camera_main.py.
    Blocks until state.running is False.
    """
    ip      = _get_ip()
    current = 0   # 0 = surveillance, 1 = info
    pulse   = 0

    print(f"[display] Stream at http://{ip}:{port}/stream")
    print(f"[display] Log UI at http://{ip}:{port}/log/ui")

    while state.running:
        pulse += 1

        if current == 0:
            _draw_surveillance(state, pulse, ip, port)
        else:
            _draw_info(state, ip, port)

        if _check_tap():
            current = (current + 1) % 2
            print(f"[display] Screen: {'surveillance' if current == 0 else 'info'}")

        time.sleep(1 / 30)
