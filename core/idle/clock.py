#!/usr/bin/env python3
"""
BearBox Idle — StandBy Clock (horizontal 480x320)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
To move things around, only edit the LAYOUT and
SIZES blocks below — don't touch anything else!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import pygame
import time
import subprocess
import threading
import os
import random

# ╔══════════════════════════════════════════════╗
# ║              EDIT THIS BLOCK                 ║
# ╚══════════════════════════════════════════════╝

# ── Font sizes ────────────────────────────────
CLOCK_SIZE  = 145  # HH:MM:SS
DATE_SIZE   = 20    # date text
QUOTE_SIZE  = 15    # quote text
LABEL_SIZE  = 11    # "CPU" / "RAM" labels
STAT_SIZE   = 13    # "0.0%" values

# ── Clock position ────────────────────────────
CLOCK_ZONE  = 0.65  # 0.0–1.0 — how much of screen height the clock owns
                    # bigger = clock moves down and has more room

# ── Bottom info section ───────────────────────
SEP_GAP     = -50     # gap between clock zone and separator line
DATE_GAP    = 8     # gap between separator line and date
QUOTE_GAP   = 26    # gap between date and quote
QUOTE_LINE  = 18    # line height between quote lines

# ── Stats bars (bottom corners) ───────────────
STAT_FROM_BOTTOM = 28   # distance from bottom of screen
STAT_BAR_WIDTH   = 110  # width of CPU/RAM bars

# ── Quote timing ──────────────────────────────
TYPE_SPEED  = 0.045  # seconds per character (lower = faster typing)
QUOTE_HOLD  = 10.0   # seconds before next quote appears

# ╔══════════════════════════════════════════════╗
# ║           DON'T EDIT BELOW HERE              ║
# ╚══════════════════════════════════════════════╝

C = {
    "bg":       (0,    5,   15),
    "blue":     (0,   180, 255),
    "midblue":  (0,   120, 200),
    "dimblue":  (0,    40,  80),
    "white":    (240, 248, 255),
    "dimwhite": (100, 120, 145),
    "green":    (0,   255, 80),
    "dim":      (15,  30,  50),
    "amber":    (255, 176,  0),
    "red":      (255,  50,  50),
}

def _font(size, bold=False):
    # try custom font first
    font_path = os.path.join(os.path.dirname(__file__), "../../fonts/mycustomfont.ttf")
    if os.path.exists(font_path):
        return pygame.font.Font(font_path, size)
    # fallback to system fonts
    for name in ["DejaVu Sans Mono", "Courier New", "Courier"]:
        try:
            return pygame.font.SysFont(name, size, bold=bold)
        except:
            pass
    return pygame.font.Font(None, size)

F_CLOCK = None
F_DATE  = None
F_QUOTE = None
F_LABEL = None
F_STAT  = None

def _init_fonts():
    global F_CLOCK, F_DATE, F_QUOTE, F_LABEL, F_STAT
    F_CLOCK = _font(CLOCK_SIZE, bold=True)
    F_DATE  = _font(DATE_SIZE,  bold=True)
    F_QUOTE = _font(QUOTE_SIZE)
    F_LABEL = _font(LABEL_SIZE)
    F_STAT  = _font(STAT_SIZE,  bold=True)

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

# ── HELPERS ───────────────────────────────────────────────────
def _centered(surf, text, font, color, y):
    s = font.render(text, True, color)
    surf.blit(s, ((surf.get_width() - s.get_width()) // 2, y))
    return s.get_height()

def _draw_bar(surf, x, y, w, h, pct, color):
    pygame.draw.rect(surf, C["dim"], (x, y, w, h), border_radius=2)
    filled = int(w * min(pct / 100, 1.0))
    if filled > 0:
        pygame.draw.rect(surf, color, (x, y, filled, h), border_radius=2)
    pygame.draw.rect(surf, C["dimblue"], (x, y, w, h), 1, border_radius=2)

def _draw_scanlines(surf):
    W, H = surf.get_width(), surf.get_height()
    for y in range(0, H, 4):
        pygame.draw.line(surf, (0, 3, 12), (0, y), (W, y))

def _wrap_text(text, font, max_w):
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if font.size(test)[0] <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

# ── MAIN DRAW ─────────────────────────────────────────────────
_tick    = 0
_colon_w = None

def draw(surf):
    global _tick, _colon_w
    if F_CLOCK is None:
        _init_fonts()

    _tick += 1
    _update_quotes()

    W, H = surf.get_width(), surf.get_height()
    surf.fill(C["bg"])
    _draw_scanlines(surf)

    now  = time.localtime()
    secs = now.tm_sec

    # ── Clock ─────────────────────────────────────────────────
    h_s  = F_CLOCK.render(time.strftime("%H"), True, C["white"])
    c1_s = F_CLOCK.render(":",                 True, C["white"])   # HH:MM — never blinks
    m_s  = F_CLOCK.render(time.strftime("%M"), True, C["white"])
    c2_s = F_CLOCK.render(":",                 True,              # MM:SS — BLINKS
                           C["blue"] if secs % 2 == 0 else C["dimblue"])
    sc_s = F_CLOCK.render(f"{secs:02d}",       True, C["blue"])

    total_w    = sum(s.get_width() for s in [h_s, c1_s, m_s, c2_s, sc_s])
    clock_h    = h_s.get_height()
    clock_zone = int(H * CLOCK_ZONE)
    clock_y    = (clock_zone - clock_h) // 2
    clock_x    = (W - total_w) // 2

    x = clock_x
    for s in [h_s, c1_s, m_s, c2_s, sc_s]:
        surf.blit(s, (x, clock_y))
        x += s.get_width()

    # ── Separator ─────────────────────────────────────────────
    sep_y = clock_zone + SEP_GAP
    pygame.draw.line(surf, C["dimblue"], (20, sep_y), (W-20, sep_y), 1)

    # ── Date ─────────────────────────────────────────────────
    date_y = sep_y + DATE_GAP
    _centered(surf, time.strftime("%A  %d %B %Y").upper(), F_DATE, C["white"], date_y)

    # ── Quote ─────────────────────────────────────────────────
    quote_y = date_y + F_DATE.get_height() + QUOTE_GAP - F_DATE.get_height()
    if _quote_display:
        lines = _wrap_text(f'"{_quote_display}"', F_QUOTE, W - 60)
        for i, line in enumerate(lines[:2]):
            ls = F_QUOTE.render(line, True, C["green"])
            surf.blit(ls, ((W - ls.get_width()) // 2, quote_y + i * QUOTE_LINE))
        if _tick % 20 < 10:
            last  = lines[min(len(lines)-1, 1)]
            lw    = F_QUOTE.size(last)[0]
            cur_x = (W - lw) // 2 + lw + 2
            cur_y = quote_y + min(len(lines)-1, 1) * QUOTE_LINE
            pygame.draw.rect(surf, C["green"], (cur_x, cur_y + 2, 5, 11))

    # ── Stats ─────────────────────────────────────────────────
    stat_y  = H - STAT_FROM_BOTTOM
    cpu_pct = _stats["cpu"]
    ram_pct = _stats["ram"]
    cpu_col = C["blue"] if cpu_pct < 60 else C["amber"] if cpu_pct < 85 else C["red"]
    ram_col = C["blue"] if ram_pct < 60 else C["amber"] if ram_pct < 85 else C["red"]

    surf.blit(F_LABEL.render("CPU", True, C["dimwhite"]), (10, stat_y))
    surf.blit(F_STAT.render(f"{cpu_pct:.1f}%", True, cpu_col), (36, stat_y - 1))
    _draw_bar(surf, 10, stat_y + 14, STAT_BAR_WIDTH, 5, cpu_pct, cpu_col)

    rx = W - STAT_BAR_WIDTH - 10
    surf.blit(F_LABEL.render("RAM", True, C["dimwhite"]), (rx, stat_y))
    surf.blit(F_STAT.render(f"{ram_pct:.1f}%", True, ram_col), (rx + 28, stat_y - 1))
    _draw_bar(surf, rx, stat_y + 14, STAT_BAR_WIDTH, 5, ram_pct, ram_col)