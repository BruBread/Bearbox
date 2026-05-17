"""
profiles/games/games_display.py
Animation helpers for the games profile.
  - terminal_boot_sequence() : scrolling green-on-black boot log
  - keyboard_wait_screen()   : RED "CONNECT KEYBOARD" poll screen
  - tv_on_animation()        : CRT power-on sweep + flash
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.display import new_frame, push, font, W, H

# ── GREEN palette (matches matrix boot anim / keyboard profile) ──────────────
G = {
    "bg":       (0,  10,  0),
    "panel":    (0,  18,  0),
    "green":    (0,  255, 70),
    "midgreen": (0,  180, 40),
    "dimgreen": (0,  90,  20),
    "darkgreen":(0,  30,  8),
    "teal":     (0,  210, 140),
    "dimteal":  (0,  100, 60),
    "white":    (210, 255, 210),
    "dimwhite": (120, 160, 120),
}

# ── RED palette (matches screen_plug_adapter / offline idle) ─────────────────
R = {
    "bg":      (12, 0,  0),
    "panel":   (22, 0,  0),
    "red":     (255, 40, 40),
    "midred":  (180, 20, 20),
    "dimred":  (70,  0,  0),
    "darkred": (25,  0,  0),
    "white":   (255, 220, 220),
    "dimwhite":(140, 80, 80),
}

# ── Fonts ─────────────────────────────────────────────────────────────────────
_MONO_LG = font(size=14, bold=False)   # terminal body text
_MONO_SM = font(size=11, bold=False)   # small status
_TITLE    = font(size=22, bold=True)   # "CONNECT KEYBOARD" heading

# ── Layout constants ──────────────────────────────────────────────────────────
_LINE_H   = 18          # px per terminal line
_MARGIN_X = 12
_MARGIN_Y = 10
_MAX_LINES = (H - _MARGIN_Y * 2) // _LINE_H   # how many lines fit on screen

# ── Boot log lines (simulated doomgeneric / SDL / framebuffer output) ─────────
BOOT_LINES = [
    ("$", "sudo doomgeneric -iwad freedoom1.wad",          G["teal"],     0.08),
    (">", "V_Init: allocate screens.",                      G["dimgreen"], 0.06),
    (">", "M_LoadDefaults: Load system defaults.",          G["dimgreen"], 0.06),
    (">", "Z_Init: Init zone memory allocation daemon.",    G["dimgreen"], 0.06),
    (">", "  zone memory: 32768 KB",                       G["dimwhite"], 0.04),
    (">", "W_Init: Init WADfiles.",                        G["dimgreen"], 0.06),
    (">", "  adding /home/bearbox/freedoom-0.13.0/freedoom1.wad", G["green"], 0.10),
    (" ", "  IWAD found.",                                 G["white"],    0.12),
    (">", "M_Init: Init miscellaneous info.",               G["dimgreen"], 0.05),
    (">", "R_Init: Init DOOM refresh daemon",               G["dimgreen"], 0.05),
    (" ", "  R_Init: [.................] done.",            G["dimgreen"], 0.08),
    (">", "P_Init: Init Playfield.",                       G["dimgreen"], 0.05),
    (">", "I_Init: Init system-specific I/O, FB /dev/fb1.", G["midgreen"], 0.09),
    (">", "  framebuffer: 480x320 @ 32bpp",                G["white"],    0.10),
    (">", "I_InitSound: sound disabled (no audio device).", G["dimwhite"], 0.05),
    (">", "NET_Init: Init network subsystem.",              G["dimgreen"], 0.05),
    (" ", "  loopback only.",                              G["dimwhite"], 0.04),
    (">", "D_CheckNetGame: checking network game status.", G["dimgreen"], 0.06),
    (">", "S_Init: Setting up sound.",                     G["dimgreen"], 0.05),
    (">", "HU_Init: Setting up heads up display.",         G["dimgreen"], 0.05),
    (">", "ST_Init: Init status bar.",                     G["dimgreen"], 0.05),
    (" ", "  keyboard input: /dev/input detected.",        G["teal"],     0.10),
    (" ", "  joypad: none.",                               G["dimwhite"], 0.04),
    (" ", "",                                              G["bg"],       0.05),
    (" ", "DOOM is ready. Handing off to engine...",       G["green"],    0.15),
]


def terminal_boot_sequence():
    """
    Render scrolling green-on-black terminal lines one by one.
    Blocks until all lines are shown.
    """
    visible: list[tuple[str, str, tuple]] = []   # (prefix, text, color)

    for prefix, text, color, delay in BOOT_LINES:
        visible.append((prefix, text, color))
        if len(visible) > _MAX_LINES:
            visible = visible[-_MAX_LINES:]

        img, d = new_frame()
        img.paste(G["bg"], [0, 0, W, H])

        # subtle scanline texture — every other row slightly darker
        for row in range(0, H, 2):
            d.line([(0, row), (W, row)], fill=G["darkgreen"])

        y = _MARGIN_Y
        for i, (pfx, txt, col) in enumerate(visible):
            # dim older lines
            age   = len(visible) - 1 - i
            alpha = max(0.25, 1.0 - age * 0.055)
            faded = tuple(int(c * alpha) for c in col)

            if pfx in ("$", ">"):
                pfx_col = G["teal"] if pfx == "$" else G["dimteal"]
                d.text((_MARGIN_X, y), pfx, font=_MONO_LG, fill=pfx_col)
                d.text((_MARGIN_X + 14, y), txt, font=_MONO_LG, fill=faded)
            else:
                d.text((_MARGIN_X + 14, y), txt, font=_MONO_LG, fill=faded)
            y += _LINE_H

        # blinking cursor on last line
        if int(time.time() * 2) % 2 == 0:
            cx = _MARGIN_X + 14
            cy = y
            d.rectangle([cx, cy, cx + 7, cy + _LINE_H - 2], fill=G["green"])

        push(img)
        time.sleep(delay)


def keyboard_wait_screen(pulse: bool = True):
    """
    Draw a single frame of the "CONNECT KEYBOARD" screen.
    RED palette, same layout as screen_plug_adapter.py.
    Call in a loop; returns immediately after one draw.
    pulse: if True, border brightness pulses on the 1-second heartbeat.
    """
    img, d = new_frame()
    img.paste(R["bg"], [0, 0, W, H])

    t      = time.time()
    bright = pulse and (int(t * 2) % 2 == 0)
    border = R["red"] if bright else R["midred"]
    inner  = R["dimred"]

    # outer border
    d.rectangle([0, 0, W - 1, H - 1], outline=border, width=2)
    # inner border
    d.rectangle([4, 4, W - 5, H - 5], outline=inner, width=1)

    # icon area — simple keyboard outline
    kx, ky, kw, kh = W // 2 - 52, 60, 104, 44
    d.rectangle([kx, ky, kx + kw, ky + kh], outline=border, width=2)
    # key rows (decorative)
    for row in range(3):
        for col in range(7):
            bx = kx + 6 + col * 13
            by = ky + 6 + row * 12
            d.rectangle([bx, by, bx + 9, by + 8], outline=R["midred"], width=1)

    # "NO KEYBOARD" label
    d.text((W // 2, 120), "NO KEYBOARD", font=_TITLE, fill=R["red"], anchor="mm")

    # sub-label
    d.text((W // 2, 148), "connect a USB keyboard to continue",
           font=_MONO_SM, fill=R["dimwhite"], anchor="mm")

    # pulsing dots to show we're polling
    dot_count = int(t * 1.5) % 4
    dots = "." * dot_count + " " * (3 - dot_count)
    d.text((W // 2, 168), f"waiting{dots}",
           font=_MONO_SM, fill=R["dimred"] if not bright else R["midred"],
           anchor="mm")

    # bottom hint
    d.text((W // 2, H - 16), "BearBox  //  GAMES",
           font=_MONO_SM, fill=R["dimred"], anchor="mm")

    push(img)


def tv_on_animation():
    """
    CRT power-on effect (~1.5 s):
      1. Black screen (3 frames)
      2. Fast horizontal scanline sweep from centre outward
      3. White flash (2 frames)
      4. Fade to black (8 frames)
    Blocks until complete.
    """
    # --- phase 1: black ---
    for _ in range(3):
        img, d = new_frame()
        img.paste((0, 0, 0), [0, 0, W, H])
        push(img)
        time.sleep(0.04)

    # --- phase 2: scanline sweep ---
    cy      = H // 2
    steps   = 22
    max_rad = H // 2 + 2
    for i in range(steps + 1):
        frac = i / steps
        rad  = int(frac * max_rad)

        img, d = new_frame()
        img.paste((0, 0, 0), [0, 0, W, H])

        # draw the sweep band — bright white core, dim edges
        for dy in range(-rad, rad + 1):
            y = cy + dy
            if 0 <= y < H:
                dist   = abs(dy)
                bright = max(0, 1.0 - dist / max(1, rad) * 1.2)
                val    = int(bright ** 1.5 * 255)
                d.line([(0, y), (W, y)], fill=(val, val, val))

        push(img)
        time.sleep(0.022)

    # --- phase 3: white flash ---
    for _ in range(2):
        img, d = new_frame()
        img.paste((255, 255, 255), [0, 0, W, H])
        push(img)
        time.sleep(0.05)

    # --- phase 4: fade to black ---
    fade_steps = 10
    for i in range(fade_steps + 1):
        frac = 1.0 - i / fade_steps
        val  = int(frac * 255)
        img, d = new_frame()
        img.paste((val, val, val), [0, 0, W, H])
        push(img)
        time.sleep(0.045)

    # hold black
    img, d = new_frame()
    img.paste((0, 0, 0), [0, 0, W, H])
    push(img)
    time.sleep(0.1)
