#!/usr/bin/env python3
"""
BearBox Idle — Offline Clock
Same layout as clock.py but full red color scheme.
Shows when Pi has no internet connection.
"""

import time
import subprocess
import threading
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_text_centered, draw_scanlines, wrap_text, font, W, H

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

CLOCK_SIZE       = 120
AMPM_SIZE        = 18
DATE_SIZE        = 20
QUOTE_SIZE       = 15
LABEL_SIZE       = 11
STAT_SIZE        = 13

CLOCK_ZONE       = 0.65
SEP_GAP          = 4
DATE_GAP         = 8
QUOTE_GAP        = 6
QUOTE_LINE       = 18
CORNER_PAD       = 8
AMPM_OFFSET_X    = 4
AMPM_OFFSET_Y    = 0
NETWORK_SIZE     = 12
NETWORK_OFFSET_Y = -8

TYPE_SPEED       = 0.045
QUOTE_HOLD       = 10.0

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

# RED palette
R = {
    "bg":      (12,  0,   0),
    "red":     (255, 40,  40),
    "midred":  (200, 20,  20),
    "dimred":  (80,  0,   0),
    "darkred": (30,  0,   0),
    "white":   (255, 220, 220),
    "dimwhite":(140, 80,  80),
    "amber":   (255, 140, 0),
    "panel":   (20,  0,   0),
}

_stats = {
    "cpu": 0.0, "ram": 0.0, "ram_used": 0,
    "ram_total": 0, "temp": 0.0,
    "disk_used": 0.0, "disk_total": 0.0,
}

def _update_stats():
    while True:
        try:
            cpu = subprocess.run("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
                shell=True, capture_output=True, text=True).stdout.strip()
            _stats["cpu"] = float(cpu) if cpu else 0.0
            mem = subprocess.run("free -m | awk 'NR==2{print $2, $3}'",
                shell=True, capture_output=True, text=True).stdout.strip().split()
            if len(mem) == 2:
                _stats["ram_total"] = int(mem[0])
                _stats["ram_used"]  = int(mem[1])
                _stats["ram"]       = (_stats["ram_used"] / _stats["ram_total"]) * 100
            temp = subprocess.run("cat /sys/class/thermal/thermal_zone0/temp",
                shell=True, capture_output=True, text=True).stdout.strip()
            _stats["temp"] = float(temp) / 1000.0 if temp else 0.0
            disk = subprocess.run("df -BM / | awk 'NR==2{print $3, $2}'",
                shell=True, capture_output=True, text=True).stdout.strip().split()
            if len(disk) == 2:
                _stats["disk_used"]  = float(disk[0].replace("M", "")) / 1024
                _stats["disk_total"] = float(disk[1].replace("M", "")) / 1024
        except:
            pass
        time.sleep(3)

threading.Thread(target=_update_stats, daemon=True).start()

# ── QUOTES ────────────────────────────────────────────────────
def _load_quotes():
    dirs = [os.path.dirname(__file__),
            os.path.join(os.path.dirname(__file__), ".."),
            os.path.join(os.path.dirname(__file__), "../..")]
    for d in dirs:
        path = os.path.join(d, "quotes.txt")
        if os.path.exists(path):
            with open(path) as f:
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
    pool = [q for q in _quotes if q != _last_quote] or _quotes
    pick = random.choice(pool)
    _last_quote = pick
    return pick

def _update_quotes():
    global _quote_display, _quote_target, _quote_char, _quote_timer, _type_timer
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
    cpu_col  = R["red"] if cpu_pct < 60 else R["amber"] if cpu_pct < 85 else (255,80,0)
    temp_col = R["red"] if temp    < 60 else R["amber"] if temp    < 75 else (255,80,0)
    d.text((CORNER_PAD, CORNER_PAD),      "CPU", font=F["label"], fill=R["dimwhite"])
    d.text((CORNER_PAD, CORNER_PAD + 14), f"{cpu_pct:.1f}%", font=F["stat"], fill=cpu_col)
    d.text((CORNER_PAD+55, CORNER_PAD+14), f"{temp:.1f}C",  font=F["stat"], fill=temp_col)

def _corner_tr(d, F):
    ram_pct = _stats["ram"]
    ram_col = R["red"] if ram_pct < 60 else R["amber"] if ram_pct < 85 else (255,80,0)
    ram_str = f"{ram_pct:.1f}%"
    lbl_w   = F["label"].getbbox("RAM")[2]
    val_w   = F["stat"].getbbox(ram_str)[2]
    d.text((W-CORNER_PAD-lbl_w, CORNER_PAD),      "RAM", font=F["label"], fill=R["dimwhite"])
    d.text((W-CORNER_PAD-val_w, CORNER_PAD + 14), ram_str, font=F["stat"],  fill=ram_col)

def _corner_bl(d, F):
    used  = _stats["disk_used"]
    total = _stats["disk_total"]
    pct   = (used/total*100) if total > 0 else 0
    col   = R["red"] if pct < 70 else R["amber"] if pct < 90 else (255,80,0)
    d.text((CORNER_PAD, H-CORNER_PAD-30), "DISK", font=F["label"], fill=R["dimwhite"])
    d.text((CORNER_PAD, H-CORNER_PAD-16), f"{used:.1f}/{total:.1f}GB",
           font=F["stat"], fill=col)

def _corner_br(d, F):
    ap_ip = "10.0.0.1"
    lbl_w = F["label"].getbbox("AP")[2]
    val_w = F["stat"].getbbox(ap_ip)[2]
    d.text((W-CORNER_PAD-lbl_w, H-CORNER_PAD-30), "AP",    font=F["label"], fill=R["dimwhite"])
    d.text((W-CORNER_PAD-val_w, H-CORNER_PAD-16), ap_ip,   font=F["stat"],  fill=R["red"])

# ── MAIN DRAW ─────────────────────────────────────────────────
_tick = 0

def draw():
    global _tick
    _tick += 1
    _update_quotes()

    F   = _fonts()
    now = time.localtime()
    sec = now.tm_sec

    img, d = new_frame(bg=R["bg"])

    # red scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))

    def tw(txt, f): return f.getbbox(txt)[2] - f.getbbox(txt)[0]
    def th(txt, f): return f.getbbox(txt)[3] - f.getbbox(txt)[1]

    hour_12 = time.strftime("%I")
    am_pm   = time.strftime("%p")
    min_str = time.strftime("%M")

    parts = [
        (hour_12, R["white"]),
        (":",     R["white"]),
        (min_str, R["white"]),
        (":",     R["red"] if sec % 2 == 0 else R["dimred"]),
        (f"{sec:02d}", R["red"]),
    ]

    total_w    = sum(tw(p[0], F["clock"]) for p in parts)
    clock_h    = th("0", F["clock"])
    clock_zone = int(H * CLOCK_ZONE)
    clock_y    = (clock_zone - clock_h) // 2
    x          = (W - total_w) // 2

    for text, color in parts:
        d.text((x, clock_y), text, font=F["clock"], fill=color)
        x += tw(text, F["clock"])

    # AM/PM
    ampm_x = (W-total_w)//2 + total_w + AMPM_OFFSET_X
    ampm_h = th(am_pm, F["ampm"])
    ampm_y = clock_y + clock_h - ampm_h + AMPM_OFFSET_Y
    d.text((ampm_x, ampm_y), am_pm, font=F["ampm"], fill=R["midred"])

    # OFFLINE label above clock
    ol_str = "OFFLINE"
    ow     = F["network"].getbbox(ol_str)[2]
    oh     = F["network"].getbbox(ol_str)[3]
    net_y  = clock_y + NETWORK_OFFSET_Y - oh
    d.text(((W-ow)//2, net_y), ol_str, font=F["network"], fill=R["dimred"])

    # separator
    sep_y = clock_zone + SEP_GAP
    d.line([(20, sep_y), (W-20, sep_y)], fill=R["dimred"], width=1)

    # date
    date_y = sep_y + DATE_GAP
    draw_text_centered(d, time.strftime("%A  %d %B %Y").upper(),
                       F["date"], R["white"], date_y)

    # quote
    quote_y = date_y + DATE_SIZE + QUOTE_GAP
    if _quote_display:
        lines = wrap_text(f'"{_quote_display}"', F["quote"], W-60)
        for i, line in enumerate(lines[:2]):
            lw = F["quote"].getbbox(line)[2] - F["quote"].getbbox(line)[0]
            d.text(((W-lw)//2, quote_y + i*QUOTE_LINE),
                   line, font=F["quote"], fill=R["red"])
        if _tick % 20 < 10:
            last  = lines[min(len(lines)-1, 1)]
            lw    = F["quote"].getbbox(last)[2] - F["quote"].getbbox(last)[0]
            cur_x = (W-lw)//2 + lw + 2
            cur_y = quote_y + min(len(lines)-1, 1) * QUOTE_LINE
            d.rectangle([cur_x, cur_y+2, cur_x+5, cur_y+13], fill=R["red"])

    # corners
    _corner_tl(d, F)
    _corner_tr(d, F)
    _corner_bl(d, F)
    _corner_br(d, F)

    push(img)

if __name__ == "__main__":
    print("Offline clock — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)
