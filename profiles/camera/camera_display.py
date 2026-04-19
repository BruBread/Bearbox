#!/usr/bin/env python3
"""
BearBox Camera — LCD Display

Two screens, tap to cycle:
  0 — SURVEILLANCE ACTIVE  (AI status + stream URL + latest description)
  1 — INFO                 (FPS, motion count, last motion, IP, AI status)

Reads from DetectionState only — no camera or inference access here.
Uses its own local _check_tap() (camera runs as a separate process).
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

from display import new_frame, push, font, draw_corner_brackets, W, H

A = {
    "bg":        (0,    5,   15),
    "amber":     (255, 176,   0),
    "dimamber":  (120,  70,   0),
    "darkamber": (20,   10,   0),
    "panel":     (5,    15,  30),
    "white":     (240, 248, 255),
    "dimwhite":  (100, 120, 145),
    "red":       (255,  50,  50),
    "dimred":    (120,  20,  20),
    "green":     (0,   255,  80),
    "dimgreen":  (0,    80,  35),
}

# AI status → (display text, color)
_AI_STYLE = {
    "IDLE":          ("IDLE",          A["dimamber"]),
    "AUTO OFF":      ("AUTO OFF",      A["dimwhite"]),
    "SEARCHING...":  ("SEARCHING...",  A["amber"]),
    "SENDING...":    ("SENDING...",    A["amber"]),
    "COOLDOWN":      ("COOLDOWN",      A["dimwhite"]),
    "NO CONNECTION": ("NO CONNECTION", A["red"]),
    "TIMEOUT":       ("TIMEOUT",       A["red"]),
    "ERROR":         ("ERROR",         A["red"]),
    "NO LAPTOP IP":  ("NO LAPTOP IP",  A["red"]),
}

# ── Touch — local copy (camera is a separate process) ─────────
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
                        struct.unpack(_evt_fmt, data)
                    except struct.error:
                        pass
            now = time.time()
            if now - _last_tap > TAP_COOLDOWN:
                _last_tap = now
                return True
    except Exception:
        _touch_fd = None
    return False


# ── Helpers ────────────────────────────────────────────────────

def _get_ip():
    try:
        out = subprocess.run(
            "hostname -I", shell=True, capture_output=True, text=True
        ).stdout.strip()
        return out.split()[0] if out else "unknown"
    except Exception:
        return "unknown"


def _fmt_elapsed(ts):
    if ts is None:
        return "never"
    elapsed = time.time() - ts
    if elapsed < 60:
        return f"{int(elapsed)}s ago"
    elif elapsed < 3600:
        return f"{int(elapsed // 60)}m ago"
    else:
        return f"{int(elapsed // 3600)}h ago"


def _truncate(text, font_obj, max_width):
    """Truncate text with ellipsis to fit max_width pixels."""
    if font_obj.getbbox(text)[2] <= max_width:
        return text
    while text and font_obj.getbbox(text + "...")[2] > max_width:
        text = text[:-1]
    return text + "..."


# ── Screen 0 — SURVEILLANCE ACTIVE ────────────────────────────

def _draw_surveillance(state, pulse, ip, port):
    status  = state.get_status()
    motion  = status["motion"]
    ai_stat = status.get("ai_status", "IDLE")
    desc    = status.get("latest_description")

    F_big   = font(52, bold=True)
    F_med   = font(18, bold=True)
    F_small = font(13)
    F_tiny  = font(11)

    img, d = new_frame(bg=A["bg"])

    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    bracket_col = A["red"] if motion else A["amber"]
    draw_corner_brackets(d, bracket_col, size=18, thickness=2)

    dot_amp = abs((pulse % 30) - 15) / 15.0
    dot_col = (int(200 + dot_amp * 55), 30, 30) if motion else A["dimamber"]
    d.ellipse([W // 2 - 6, 18, W // 2 + 6, 30], fill=dot_col)

    label = "SURVEILLANCE"
    lw    = F_big.getbbox(label)[2]
    d.text(((W - lw) // 2, 38), label, font=F_big, fill=A["amber"])

    label2 = "MOTION!" if motion else "ACTIVE"
    col2   = A["red"] if motion else A["dimwhite"]
    lw2    = F_med.getbbox(label2)[2]
    d.text(((W - lw2) // 2, 96), label2, font=F_med, fill=col2)

    d.line([(30, 122), (W - 30, 122)], fill=A["dimamber"], width=1)

    # AI status row with pulsing dot
    ai_text, ai_col = _AI_STYLE.get(ai_stat, (ai_stat[:14], A["dimwhite"]))
    pulsing = ai_stat in ("SENDING...", "SEARCHING...")
    if pulsing:
        pulse_frac = abs((pulse % 20) - 10) / 10.0
        dot_c = (int(120 + pulse_frac * 135), int(50 + pulse_frac * 126), 0)
    else:
        dot_c = ai_col

    row_y  = 130
    ai_lbl = "AI"
    ai_lw  = F_tiny.getbbox(ai_lbl)[2]
    d.text((30, row_y), ai_lbl, font=F_tiny, fill=A["dimamber"])
    d.ellipse([30 + ai_lw + 6, row_y + 3,
               30 + ai_lw + 12, row_y + 9], fill=dot_c)
    d.text((30 + ai_lw + 18, row_y), ai_text, font=F_tiny, fill=ai_col)

    d.line([(30, 148), (W - 30, 148)], fill=A["darkamber"], width=1)

    # Latest description (truncated to fit one line)
    if desc:
        desc_trunc = _truncate(desc, F_tiny, W - 60)
        d.text((30, 153), desc_trunc, font=F_tiny, fill=A["dimwhite"])

    # Stream URL
    url = f"http://{ip}:{port}/stream"
    uw  = F_small.getbbox(url)[2]
    d.text(((W - uw) // 2, 172), url, font=F_small, fill=A["dimwhite"])

    hint = "open in browser to view"
    hw   = F_tiny.getbbox(hint)[2]
    d.text(((W - hw) // 2, 190), hint, font=F_tiny, fill=A["dimamber"])

    d.rectangle([0, H - 24, W, H], fill=A["panel"])
    foot = "tap for info"
    fw   = F_tiny.getbbox(foot)[2]
    d.text(((W - fw) // 2, H - 16), foot, font=F_tiny, fill=A["dimamber"])

    push(img)


# ── Screen 1 — INFO ────────────────────────────────────────────

def _draw_info(state, ip, port):
    status  = state.get_status()
    ai_stat = status.get("ai_status", "IDLE")
    _, ai_col = _AI_STYLE.get(ai_stat, (ai_stat, A["dimwhite"]))

    F_hdr  = font(16, bold=True)
    F_lbl  = font(13)
    F_val  = font(15, bold=True)
    F_tiny = font(11)

    img, d = new_frame(bg=A["bg"])
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(0, 8, 18))

    d.rectangle([0, 0, W, 38], fill=A["panel"])
    d.line([(0, 38), (W, 38)], fill=A["dimamber"], width=1)
    title = "CAMERA INFO"
    tw    = F_hdr.getbbox(title)[2]
    d.text(((W - tw) // 2, 10), title, font=F_hdr, fill=A["amber"])

    rows = [
        ("FPS",           f"{status['fps']:.1f}",              A["white"]),
        ("MOTION EVENTS", str(status["motion_count"]),
         A["red"] if status["motion_count"] > 0 else A["dimwhite"]),
        ("LAST MOTION",   _fmt_elapsed(status["last_motion"]),  A["dimwhite"]),
        ("STATUS",        "MOTION" if status["motion"] else "CLEAR",
         A["red"] if status["motion"] else A["green"]),
        ("AI",            ai_stat[:14],                         ai_col),
        ("STREAM",        f":{port}/stream",                    A["dimamber"]),
        ("IP",            ip,                                   A["dimwhite"]),
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

    d.rectangle([0, H - 24, W, H], fill=A["panel"])
    foot = "tap to go back"
    fw   = F_tiny.getbbox(foot)[2]
    d.text(((W - fw) // 2, H - 16), foot, font=F_tiny, fill=A["dimamber"])

    push(img)


# ── Main display loop ──────────────────────────────────────────

def run_display(state, port=80):
    """LCD display loop. Runs on the main thread. Blocks until state.running is False."""
    ip      = _get_ip()
    current = 0
    pulse   = 0

    print(f"[display] Stream at http://{ip}:{port}/stream")

    while state.running:
        pulse += 1

        if current == 0:
            _draw_surveillance(state, pulse, ip, port)
        else:
            _draw_info(state, ip, port)

        if _check_tap():
            current = (current + 1) % 2
            print(f"[display] → {'surveillance' if current == 0 else 'info'}")

        time.sleep(1 / 30)
