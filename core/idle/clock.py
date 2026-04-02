#!/usr/bin/env python3
"""
BearBox Idle — StandBy Clock
Pillow + direct framebuffer (no pygame/SDL needed)
480x320 landscape

Corner overlays:
  Top Left     — CPU % bar
  Top Right    — RAM % bar
  Bottom Left  — Storage used/total bar
  Bottom Right — IP address
  Top Center   — Temperature segmented bar
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

# ── Font sizes ────────────────────────────────
CLOCK_SIZE   = 120    # HH:MM:SS font size
AMPM_SIZE    = 18     # AM/PM indicator size
NETWORK_SIZE = 12     # network name size
DATE_SIZE    = 20     # date text size
QUOTE_SIZE   = 15     # quote text size
LABEL_SIZE   = 11     # corner label size
STAT_SIZE    = 13     # corner value size

# ── Clock layout ──────────────────────────────
CLOCK_ZONE   = 0.65   # 0.0-1.0, how much screen height clock owns

# ── Network name (above clock) ────────────────
NETWORK_OFFSET_Y = 0  # pixels above the clock (negative = higher up)
                       # 0 = right above clock, -20 = higher, +10 = closer

# ── AM/PM indicator (next to seconds) ─────────
AMPM_OFFSET_X = 4     # pixels right of seconds
AMPM_OFFSET_Y = 0     # pixels from bottom of clock (0 = aligned with seconds bottom)

# ── Separator line ────────────────────────────
SEP_GAP      = 4      # gap between clock zone bottom and separator line

# ── Date (below separator) ────────────────────
DATE_GAP     = 8      # gap between separator and date

# ── Quote (below date) ────────────────────────
QUOTE_GAP    = 6      # gap between date and quote
QUOTE_LINE   = 18     # line height between wrapped quote lines

# ── Corner stats ──────────────────────────────
CORNER_PAD   = 8      # padding from screen edges

# ── Corner bar dimensions ─────────────────────
BAR_W        = 60     # width of corner stat bars
BAR_H        = 5      # height of corner stat bars

# ── Temperature bar (top center) ──────────────
TEMP_BAR_W      = 80   # total width of the segmented bar
TEMP_BAR_H      = 6    # height of each segment
TEMP_SEG_COUNT  = 10   # number of segments
TEMP_SEG_GAP    = 2    # gap between segments
TEMP_BAR_Y      = 5    # Y position from top of screen
TEMP_LABEL_SIZE = 10   # label font size
# Thresholds (°C): green=okay, yellow=concerning, red=BAD
TEMP_GREEN_MAX  = 60
TEMP_YELLOW_MAX = 75

# ── Quote timing ──────────────────────────────
TYPE_SPEED   = 0.045  # seconds per character
QUOTE_HOLD   = 10.0   # seconds before next quote

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

# ── STATS ─────────────────────────────────────────────────────
_stats = {
    "cpu":        0.0,
    "ram":        0.0,
    "ram_used":   0,
    "ram_total":  0,
    "temp":       0.0,
    "disk_used":  0.0,
    "disk_total": 0.0,
    "ip":         "---",
    "network":    "---",
}

def _update_stats():
    while True:
        try:
            # CPU %
            cpu = subprocess.run(
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            _stats["cpu"] = float(cpu) if cpu else 0.0

            # RAM
            mem = subprocess.run(
                "free -m | awk 'NR==2{print $2, $3}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip().split()
            if len(mem) == 2:
                _stats["ram_total"] = int(mem[0])
                _stats["ram_used"]  = int(mem[1])
                _stats["ram"]       = (_stats["ram_used"] / _stats["ram_total"]) * 100

            # CPU temperature
            temp = subprocess.run(
                "cat /sys/class/thermal/thermal_zone0/temp",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            _stats["temp"] = float(temp) / 1000.0 if temp else 0.0

            # Storage
            disk = subprocess.run(
                "df -BM / | awk 'NR==2{print $3, $2}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip().split()
            if len(disk) == 2:
                _stats["disk_used"]  = float(disk[0].replace("M", "")) / 1024
                _stats["disk_total"] = float(disk[1].replace("M", "")) / 1024

            # IP
            ip = subprocess.run(
                "hostname -I | awk '{print $1}'",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            _stats["ip"] = ip if ip else "---"

            # Network SSID
            ssid = subprocess.run(
                "iwgetid -r 2>/dev/null || nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes' | cut -d: -f2",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            _stats["network"] = ssid if ssid else "No WiFi"

        except:
            pass
        time.sleep(3)

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
_F = {}

def _fonts():
    if not _F:
        _F["clock"]   = font(CLOCK_SIZE,   bold=True)
        _F["ampm"]    = font(AMPM_SIZE,    bold=True)
        _F["network"] = font(NETWORK_SIZE)
        _F["date"]    = font(DATE_SIZE,    bold=True)
        _F["quote"]   = font(QUOTE_SIZE)
        _F["label"]   = font(LABEL_SIZE)
        _F["stat"]    = font(STAT_SIZE,    bold=True)
        _F["templbl"] = font(TEMP_LABEL_SIZE)
    return _F

# ── HELPER: slim filled bar ───────────────────────────────────
def _draw_stat_bar(d, x, y, pct, color, w=BAR_W, h=BAR_H):
    """Dim-outlined track with a filled portion scaled to pct (0–100)."""
    # track outline
    d.rectangle([x, y, x + w, y + h], outline=C["dimblue"])
    # fill
    fill_w = max(2, int(w * min(pct, 100) / 100))
    d.rectangle([x + 1, y + 1, x + fill_w - 1, y + h - 1], fill=color)

# ── HELPER: segmented temperature bar (top center) ────────────
def _draw_temp_bar(d, F, temp):
    """
    Segmented bar centered at top of screen.
    green  < TEMP_GREEN_MAX °C
    yellow < TEMP_YELLOW_MAX °C
    red    ≥ TEMP_YELLOW_MAX °C
    """
    if temp < TEMP_GREEN_MAX:
        bar_color = C["green"]
    elif temp < TEMP_YELLOW_MAX:
        bar_color = C["amber"]
    else:
        bar_color = C["red"]

    # map 0–90 °C → 0–100%
    temp_pct = min(max(temp / 90.0, 0.0), 1.0)
    lit_segs = int(temp_pct * TEMP_SEG_COUNT)

    seg_w   = (TEMP_BAR_W - (TEMP_SEG_COUNT - 1) * TEMP_SEG_GAP) // TEMP_SEG_COUNT
    start_x = (W - TEMP_BAR_W) // 2
    y       = TEMP_BAR_Y

    for i in range(TEMP_SEG_COUNT):
        sx = start_x + i * (seg_w + TEMP_SEG_GAP)
        if i < lit_segs:
            d.rectangle([sx, y, sx + seg_w, y + TEMP_BAR_H], fill=bar_color)
        else:
            d.rectangle([sx, y, sx + seg_w, y + TEMP_BAR_H], outline=C["dimblue"])

    # tiny °C label just right of the bar
    label = f"{temp:.0f}C"
    lx = start_x + TEMP_BAR_W + 5
    ly = y - 1
    d.text((lx, ly), label, font=F["templbl"], fill=bar_color)

# ── CORNERS ───────────────────────────────────────────────────

def _corner_tl(d, F):
    """Top-left: CPU label + percentage + bar"""
    cpu_pct = _stats["cpu"]
    col     = C["blue"] if cpu_pct < 60 else C["amber"] if cpu_pct < 85 else C["red"]
    val_str = f"{cpu_pct:.0f}%"

    # "CPU  42%" on one line
    d.text((CORNER_PAD, CORNER_PAD),
           "CPU", font=F["label"], fill=C["dimwhite"])
    lbl_w = F["label"].getbbox("CPU")[2]
    d.text((CORNER_PAD + lbl_w + 4, CORNER_PAD),
           val_str, font=F["label"], fill=col)
    # bar below
    _draw_stat_bar(d, CORNER_PAD, CORNER_PAD + 14, cpu_pct, col)

def _corner_tr(d, F):
    """Top-right: RAM label + percentage + bar"""
    ram_pct = _stats["ram"]
    col     = C["blue"] if ram_pct < 60 else C["amber"] if ram_pct < 85 else C["red"]
    val_str = f"{ram_pct:.0f}%"

    bar_x   = W - CORNER_PAD - BAR_W
    lbl_w   = F["label"].getbbox("RAM")[2]
    val_w   = F["label"].getbbox(val_str)[2]

    # right-align "RAM" then value to the left of it
    d.text((W - CORNER_PAD - lbl_w, CORNER_PAD),
           "RAM", font=F["label"], fill=C["dimwhite"])
    d.text((bar_x - val_w - 4, CORNER_PAD),
           val_str, font=F["label"], fill=col)
    _draw_stat_bar(d, bar_x, CORNER_PAD + 14, ram_pct, col)

def _corner_bl(d, F):
    """Bottom-left: Disk label + used/total + bar"""
    used    = _stats["disk_used"]
    total   = _stats["disk_total"]
    pct     = (used / total * 100) if total > 0 else 0
    col     = C["blue"] if pct < 70 else C["amber"] if pct < 90 else C["red"]
    val_str = f"{used:.1f}/{total:.1f}G"

    bar_y   = H - CORNER_PAD - BAR_H
    label_y = bar_y - 16

    d.text((CORNER_PAD, label_y),
           "DISK", font=F["label"], fill=C["dimwhite"])
    lbl_w = F["label"].getbbox("DISK")[2]
    d.text((CORNER_PAD + lbl_w + 4, label_y),
           val_str, font=F["label"], fill=col)
    _draw_stat_bar(d, CORNER_PAD, bar_y, pct, col)

def _corner_br(d, F):
    """Bottom-right: IP address (text — no sensible bar for an IP)"""
    ip    = _stats["ip"]
    lbl_w = F["label"].getbbox("IP")[2]
    val_w = F["stat"].getbbox(ip)[2]
    d.text((W - CORNER_PAD - lbl_w, H - CORNER_PAD - 30),
           "IP", font=F["label"], fill=C["dimwhite"])
    d.text((W - CORNER_PAD - val_w, H - CORNER_PAD - 16),
           ip, font=F["stat"], fill=C["blue"])

# ── MAIN DRAW ─────────────────────────────────────────────────
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

    # ── Temperature bar (top center) ─────────────────────────
    _draw_temp_bar(d, F, _stats["temp"])

    # ── Clock (12hr format) ───────────────────────────────────
    def tw(txt, f): return f.getbbox(txt)[2] - f.getbbox(txt)[0]
    def th(txt, f): return f.getbbox(txt)[3] - f.getbbox(txt)[1]

    hour_12  = time.strftime("%I")
    am_pm    = time.strftime("%p")
    min_str  = time.strftime("%M")
    sec_str  = f"{sec:02d}"

    parts = [
        (hour_12,  C["white"]),
        (":",      C["white"]),
        (min_str,  C["white"]),
        (":",      C["blue"] if sec % 2 == 0 else C["dimblue"]),
        (sec_str,  C["blue"]),
    ]

    total_w    = sum(tw(p[0], F["clock"]) for p in parts)
    clock_h    = th("0", F["clock"])
    clock_zone = int(H * CLOCK_ZONE)
    clock_y    = (clock_zone - clock_h) // 2
    x          = (W - total_w) // 2

    for text, color in parts:
        d.text((x, clock_y), text, font=F["clock"], fill=color)
        x += tw(text, F["clock"])

    # ── AM/PM indicator ───────────────────────────────────────
    ampm_x = (W - total_w) // 2 + total_w + AMPM_OFFSET_X
    ampm_h = th(am_pm, F["ampm"])
    ampm_y = clock_y + clock_h - ampm_h + AMPM_OFFSET_Y
    d.text((ampm_x, ampm_y), am_pm, font=F["ampm"], fill=C["midblue"])

    # ── Network name (above clock) ────────────────────────────
    network     = _stats["network"]
    network_str = f"  {network}  "
    nw          = F["network"].getbbox(network_str)[2]
    nh          = F["network"].getbbox(network_str)[3]
    net_y       = clock_y + NETWORK_OFFSET_Y - nh
    d.text(((W - nw) // 2, net_y), network_str,
           font=F["network"], fill=C["white"])

    # ── Separator ─────────────────────────────────────────────
    sep_y = clock_zone + SEP_GAP
    d.line([(20, sep_y), (W-20, sep_y)], fill=C["dimblue"], width=1)

    # ── Date ──────────────────────────────────────────────────
    date_y = sep_y + DATE_GAP
    draw_text_centered(d, time.strftime("%A  %d %B %Y").upper(),
                       F["date"], C["white"], date_y)

    # ── Quote ─────────────────────────────────────────────────
    quote_y = date_y + DATE_SIZE + QUOTE_GAP
    if _quote_display:
        lines = wrap_text(f'"{_quote_display}"', F["quote"], W - 60)
        for i, line in enumerate(lines[:2]):
            lw = F["quote"].getbbox(line)[2] - F["quote"].getbbox(line)[0]
            d.text(((W - lw) // 2, quote_y + i * QUOTE_LINE),
                   line, font=F["quote"], fill=C["green"])
        if _tick % 20 < 10:
            last  = lines[min(len(lines)-1, 1)]
            lw    = F["quote"].getbbox(last)[2] - F["quote"].getbbox(last)[0]
            cur_x = (W - lw) // 2 + lw + 2
            cur_y = quote_y + min(len(lines)-1, 1) * QUOTE_LINE
            d.rectangle([cur_x, cur_y+2, cur_x+5, cur_y+13], fill=C["green"])

    # ── Corners ───────────────────────────────────────────────
    _corner_tl(d, F)
    _corner_tr(d, F)
    _corner_bl(d, F)
    _corner_br(d, F)

    push(img)

# ── STANDALONE ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running clock — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)