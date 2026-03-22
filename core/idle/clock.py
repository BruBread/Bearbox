#!/usr/bin/env python3
"""
BearBox Idle — StandBy Clock
Pillow + direct framebuffer (no pygame/SDL needed)
480x320 landscape

Corner overlays:
  Top Left     — CPU % + temperature
  Top Right    — RAM %
  Bottom Left  — Storage used/total
  Bottom Right — IP address
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
    return _F

# ── CORNERS ───────────────────────────────────────────────────

def _corner_tl(d, F):
    cpu_pct  = _stats["cpu"]
    temp     = _stats["temp"]
    cpu_col  = C["blue"]  if cpu_pct < 60 else C["amber"] if cpu_pct < 85 else C["red"]
    temp_col = C["blue"]  if temp    < 60 else C["amber"] if temp    < 75 else C["red"]
    d.text((CORNER_PAD, CORNER_PAD),
           "CPU", font=F["label"], fill=C["dimwhite"])
    d.text((CORNER_PAD, CORNER_PAD + 14),
           f"{cpu_pct:.1f}%", font=F["stat"], fill=cpu_col)
    d.text((CORNER_PAD + 55, CORNER_PAD + 14),
           f"{temp:.1f}C", font=F["stat"], fill=temp_col)

def _corner_tr(d, F):
    ram_pct = _stats["ram"]
    ram_col = C["blue"] if ram_pct < 60 else C["amber"] if ram_pct < 85 else C["red"]
    ram_str = f"{ram_pct:.1f}%"
    lbl_w   = F["label"].getbbox("RAM")[2]
    val_w   = F["stat"].getbbox(ram_str)[2]
    d.text((W - CORNER_PAD - lbl_w, CORNER_PAD),
           "RAM", font=F["label"], fill=C["dimwhite"])
    d.text((W - CORNER_PAD - val_w, CORNER_PAD + 14),
           ram_str, font=F["stat"], fill=ram_col)

def _corner_bl(d, F):
    used  = _stats["disk_used"]
    total = _stats["disk_total"]
    pct   = (used / total * 100) if total > 0 else 0
    col   = C["blue"] if pct < 70 else C["amber"] if pct < 90 else C["red"]
    d.text((CORNER_PAD, H - CORNER_PAD - 30),
           "DISK", font=F["label"], fill=C["dimwhite"])
    d.text((CORNER_PAD, H - CORNER_PAD - 16),
           f"{used:.1f}/{total:.1f}GB", font=F["stat"], fill=col)

def _corner_br(d, F):
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

    # ── Clock (12hr format) ───────────────────────────────────
    def tw(txt, f): return f.getbbox(txt)[2] - f.getbbox(txt)[0]
    def th(txt, f): return f.getbbox(txt)[3] - f.getbbox(txt)[1]

    hour_12  = time.strftime("%I")   # 12-hour, zero padded
    am_pm    = time.strftime("%p")   # AM or PM
    min_str  = time.strftime("%M")
    sec_str  = f"{sec:02d}"

    parts = [
        (hour_12,  C["white"]),
        (":",      C["white"]),
        (min_str,  C["white"]),
        (":",      C["blue"] if sec % 2 == 0 else C["dimblue"]),  # blinks
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

    # ── AM/PM indicator (right of seconds, bottom aligned) ────
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