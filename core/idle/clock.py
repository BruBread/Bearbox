#!/usr/bin/env python3
"""
BearBox Idle — StandBy Clock
Pillow + direct framebuffer (no pygame/SDL needed)
480x320 landscape
"""

import time
import subprocess
import threading
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import (
    new_frame, push, draw_text_centered, draw_bar,
    draw_scanlines, wrap_text, font, C, W, H
)

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

CLOCK_SIZE       = 120    # HH:MM:SS font size
DATE_SIZE        = 20     # date text size
QUOTE_SIZE       = 15     # quote text size
LABEL_SIZE       = 11     # CPU/RAM label size
STAT_SIZE        = 13     # CPU/RAM value size

CLOCK_ZONE       = 0.65   # 0.0-1.0, how much screen height clock owns
SEP_GAP          = 4      # gap between clock zone and separator
DATE_GAP         = 8      # gap between separator and date
QUOTE_GAP        = 26     # gap between date and quote
QUOTE_LINE       = 18     # line height between quote lines

STAT_FROM_BOTTOM = 28     # distance of stats from bottom
STAT_BAR_WIDTH   = 110    # width of CPU/RAM bars

TYPE_SPEED       = 0.045  # seconds per character
QUOTE_HOLD       = 10.0   # seconds before next quote

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

# ── STATS ─────────────────────────────────────────────────────
_stats = {"cpu": 0.0, "ram": 0.0, "ram_used": 0, "ram_total": 0}

def _update_stats():
    while True:
        try:
            cpu = subprocess.run(
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            _stats["cpu"] = float(cpu) if cpu else 0.0
            mem = subprocess.run(
                "free -m | awk 'NR==2{print $2, $3}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip().split()
            if len(mem) == 2:
                _stats["ram_total"] = int(mem[0])
                _stats["ram_used"]  = int(mem[1])
                _stats["ram"]       = (_stats["ram_used"] / _stats["ram_total"]) * 100
        except:
            pass
        time.sleep(2)

threading.Thread(target=_update_stats, daemon=True).start()

# ── QUOTES ────────────────────────────────────────────────────
def _load_quotes():
    dirs = [
        os.path.dirname(__file__),
        os.path.join(os.path.dirname(__file__), ".."),
        os.path.join(os.path.dirname(__file__), "../.."),
    ]
    for d in dirs:
        path = os.path.join(d, "quotes.txt")
        if os.path.exists(path):
            with open(path, "r") as f:
                lines = [l.strip().strip('"') for l in f if l.strip()]
            return lines if lines else ["hack the planet"]
    return ["hack the planet"]

_quotes        = _load_quotes()
_quote_display = ""
_quote_target  = ""
_quote_char    = 0
_quote_timer   = 0.0
_type_timer    = 0.0
_last_quote    = ""

def _pick_random_quote():
    global _last_quote
    pool        = [q for q in _quotes if q != _last_quote] or _quotes
    pick        = random.choice(pool)
    _last_quote = pick
    return pick

def _update_quotes():
    global _quote_display, _quote_target
    global _quote_char, _quote_timer, _type_timer
    now = time.time()
    if _quote_target == "":
        _quote_target = _pick_random_quote()
        _quote_timer  = now
        _type_timer   = now
    if _quote_char < len(_quote_target):
        if now - _type_timer >= TYPE_SPEED:
            _quote_char   += 1
            _quote_display = _quote_target[:_quote_char]
            _type_timer    = now
    if _quote_char >= len(_quote_target):
        if now - _quote_timer >= QUOTE_HOLD:
            _quote_target  = _pick_random_quote()
            _quote_char    = 0
            _quote_display = ""
            _quote_timer   = now
            _type_timer    = now

# ── FONTS ─────────────────────────────────────────────────────
# pre-load so first frame isn't slow
_F = {}

def _fonts():
    if not _F:
        _F["clock"] = font(CLOCK_SIZE, bold=True)
        _F["date"]  = font(DATE_SIZE,  bold=True)
        _F["quote"] = font(QUOTE_SIZE)
        _F["label"] = font(LABEL_SIZE)
        _F["stat"]  = font(STAT_SIZE,  bold=True)
    return _F

# ── DRAW ──────────────────────────────────────────────────────
_tick = 0

def draw():
    global _tick
    _tick += 1
    _update_quotes()

    F   = _fonts()
    now = time.localtime()
    sec = now.tm_sec

    img, d = new_frame()
    draw_scanlines(d)

    # ── Clock ─────────────────────────────────────────────────
    h_str  = time.strftime("%H")
    m_str  = time.strftime("%M")
    s_str  = f"{sec:02d}"
    # always solid HH:MM colon, only MM:SS colon blinks
    full   = f"{h_str}:{m_str}:{s_str}"

    # measure each part for centering
    def tw(txt, f): return f.getbbox(txt)[2] - f.getbbox(txt)[0]
    def th(txt, f): return f.getbbox(txt)[3] - f.getbbox(txt)[1]

    parts = [
        (h_str,  C["white"]),
        (":",    C["white"]),        # HH:MM — always solid
        (m_str,  C["white"]),
        (":",    C["blue"] if sec % 2 == 0 else C["dimblue"]),  # blinks
        (s_str,  C["blue"]),
    ]

    total_w    = sum(tw(p[0], F["clock"]) for p in parts)
    clock_h    = th("0", F["clock"])
    clock_zone = int(H * CLOCK_ZONE)
    clock_y    = (clock_zone - clock_h) // 2
    x          = (W - total_w) // 2

    for text, color in parts:
        d.text((x, clock_y), text, font=F["clock"], fill=color)
        x += tw(text, F["clock"])

    # ── Separator ─────────────────────────────────────────────
    sep_y = clock_zone + SEP_GAP
    d.line([(20, sep_y), (W-20, sep_y)], fill=C["dimblue"], width=1)

    # ── Date ─────────────────────────────────────────────────
    date_y   = sep_y + DATE_GAP
    date_str = time.strftime("%A  %d %B %Y").upper()
    draw_text_centered(d, date_str, F["date"], C["white"], date_y)

    # ── Quote ─────────────────────────────────────────────────
    quote_y = date_y + DATE_SIZE + QUOTE_GAP - DATE_SIZE
    if _quote_display:
        lines = wrap_text(f'"{_quote_display}"', F["quote"], W - 60)
        for i, line in enumerate(lines[:2]):
            lw = F["quote"].getbbox(line)[2] - F["quote"].getbbox(line)[0]
            d.text(((W - lw) // 2, quote_y + i * QUOTE_LINE),
                   line, font=F["quote"], fill=C["green"])
        # blinking cursor
        if _tick % 20 < 10:
            last  = lines[min(len(lines)-1, 1)]
            lw    = F["quote"].getbbox(last)[2] - F["quote"].getbbox(last)[0]
            cur_x = (W - lw) // 2 + lw + 2
            cur_y = quote_y + min(len(lines)-1, 1) * QUOTE_LINE
            d.rectangle([cur_x, cur_y+2, cur_x+5, cur_y+13], fill=C["green"])

    # ── Stats ─────────────────────────────────────────────────
    stat_y  = H - STAT_FROM_BOTTOM
    cpu_pct = _stats["cpu"]
    ram_pct = _stats["ram"]
    cpu_col = C["blue"] if cpu_pct < 60 else C["amber"] if cpu_pct < 85 else C["red"]
    ram_col = C["blue"] if ram_pct < 60 else C["amber"] if ram_pct < 85 else C["red"]

    # CPU left
    d.text((10, stat_y),    "CPU", font=F["label"], fill=C["dimwhite"])
    d.text((36, stat_y-1),  f"{cpu_pct:.1f}%", font=F["stat"], fill=cpu_col)
    draw_bar(d, 10, stat_y+16, STAT_BAR_WIDTH, 5, cpu_pct, cpu_col)

    # RAM right
    rx = W - STAT_BAR_WIDTH - 10
    d.text((rx,    stat_y),   "RAM", font=F["label"], fill=C["dimwhite"])
    d.text((rx+28, stat_y-1), f"{ram_pct:.1f}%", font=F["stat"], fill=ram_col)
    draw_bar(d, rx, stat_y+16, STAT_BAR_WIDTH, 5, ram_pct, ram_col)

    push(img)


# ── STANDALONE TEST ───────────────────────────────────────────
if __name__ == "__main__":
    print("Running clock — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)