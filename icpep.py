#!/usr/bin/env python3
"""
ICpEP.SE Recruitment Screen for BearBox
Drop in: /home/bearbox/bearbox/icpep.py
Run:     python /home/bearbox/bearbox/icpep.py

━━━ CONFIGURE HERE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

LINES = [
    # (text,            font_size,  color)               ← color is optional; omit to use BASE/BRIGHT pulse
    ("JOIN",            84),
    ("COMPUTER",        84,         (255, 255, 255)),     # white
    ("ENGINEERING",     84),
]

LINE_SPACING = 12   # px gap between lines

# ── Color config (R, G, B) ─────────────────────────────────────
BASE_COLOR   = (0, 130, 220)
BRIGHT_COLOR = (0, 255, 255)
SHADOW_COLOR = (0,  10,  25)
GLITCH_COLOR = (0,  55,  85)

"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import time, os, sys, math, random, string, subprocess, signal
import threading, tty, termios

sys.path.insert(0, "/home/bearbox/bearbox/core")
from display import new_frame, push, font, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap

# ── LED setup ──────────────────────────────────────────────────
try:
    import lgpio
    # BOARD pins: 29,31,33,32,36,37 -> BCM: 5,6,13,12,16,26
    LED_PINS_BCM = [5, 6, 13, 12, 16, 26]
    _led_handle  = lgpio.gpiochip_open(0)
    for _pin in LED_PINS_BCM:
        lgpio.gpio_claim_output(_led_handle, _pin)
    LED_AVAILABLE = True
except Exception as e:
    print(f"[icpep] lgpio not available, LEDs disabled: {e}")
    LED_AVAILABLE = False

# ── LED helpers ────────────────────────────────────────────────
def _all_off():
    if not LED_AVAILABLE:
        return
    for pin in LED_PINS_BCM:
        lgpio.gpio_write(_led_handle, pin, 0)

def _led_write(pin, val):
    if LED_AVAILABLE:
        lgpio.gpio_write(_led_handle, pin, val)

# ── LED pattern functions ──────────────────────────────────────
def pattern_off():
    _all_off()
    time.sleep(0.1)

def pattern_all_blink():
    for pin in LED_PINS_BCM:
        _led_write(pin, 1)
    time.sleep(0.5)
    _all_off()
    time.sleep(0.5)

def pattern_alternating():
    even_pins = LED_PINS_BCM[::2]
    odd_pins  = LED_PINS_BCM[1::2]
    for p in even_pins: _led_write(p, 1)
    for p in odd_pins:  _led_write(p, 0)
    time.sleep(0.5)
    for p in even_pins: _led_write(p, 0)
    for p in odd_pins:  _led_write(p, 1)
    time.sleep(0.5)

def pattern_running_lights():
    for pin in LED_PINS_BCM:
        _all_off()
        _led_write(pin, 1)
        time.sleep(0.1)
    for pin in reversed(LED_PINS_BCM):
        _all_off()
        _led_write(pin, 1)
        time.sleep(0.1)

def pattern_chase():
    for i in range(len(LED_PINS_BCM)):
        _all_off()
        for p in LED_PINS_BCM[:i + 1]:
            _led_write(p, 1)
        time.sleep(0.1)
    for i in range(len(LED_PINS_BCM), 0, -1):
        _all_off()
        for p in LED_PINS_BCM[:i]:
            _led_write(p, 1)
        time.sleep(0.1)

def pattern_random_twinkle():
    _all_off()
    _led_write(random.choice(LED_PINS_BCM), 1)
    time.sleep(0.05)

# ── Pattern list — index 0 is always OFF ──────────────────────
LED_PATTERNS = [
    pattern_off,
    pattern_all_blink,
    pattern_alternating,
    pattern_running_lights,
    pattern_chase,
    pattern_random_twinkle,
]
LED_PATTERN_NAMES = [
    "Off",
    "All Blink",
    "Alternating",
    "Running Lights",
    "Chase",
    "Random Twinkle",
]

_led_pattern_index = 0   # start at Off
_led_lock          = threading.Lock()

def _get_pattern_index():
    with _led_lock:
        return _led_pattern_index

def _next_pattern():
    global _led_pattern_index
    with _led_lock:
        _led_pattern_index = (_led_pattern_index + 1) % len(LED_PATTERNS)
        name = LED_PATTERN_NAMES[_led_pattern_index]
    print(f"\n[icpep] LED pattern → {name}")

# ── LED runner thread ──────────────────────────────────────────
def _led_runner():
    """Continuously calls the current LED pattern function."""
    while True:
        idx = _get_pattern_index()
        LED_PATTERNS[idx]()

# ── Keyboard listener ──────────────────────────────────────────
def _keyboard_listener():
    """Listens for SPACE (next pattern) and Ctrl+C (exit)."""
    fd           = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == ' ':
                _next_pattern()
            elif ch == '\x03':   # Ctrl+C
                _cleanup()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


BLACK        = (0, 0, 0)
GLITCH_CHARS = list(string.ascii_uppercase + string.digits + "@#$%&!?|/<>[]")

# ── Color interpolation helper ────────────────────────────────
def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

# ── Build fonts from config ────────────────────────────────────
_built = []
def _build_fonts():
    global _built
    if not _built:
        _built = [(row[0], font(row[1], bold=True), row[2] if len(row) > 2 else None)
                  for row in LINES]
    return _built

# ── Service control ───────────────────────────────────────────
def _stop_service():
    subprocess.run(["sudo", "systemctl", "stop", "bearbox"], capture_output=True)

def _start_service():
    subprocess.run(["sudo", "systemctl", "start", "bearbox"], capture_output=True)

# ── Layout helper — centered block ───────────────────────────
def _layout(lines_fonts):
    total_h = sum(fnt.getbbox(txt)[3] for txt, fnt, _ in lines_fonts)
    total_h += LINE_SPACING * (len(lines_fonts) - 1)
    y = (H - total_h) // 2
    result = []
    for txt, fnt, line_color in lines_fonts:
        th = fnt.getbbox(txt)[3]
        tw = fnt.getbbox(txt)[2]
        x  = (W - tw) // 2
        result.append((txt, fnt, x, y, th, line_color))
        y += th + LINE_SPACING
    return result

# ── CRT shutdown animation ────────────────────────────────────
def _play_shutdown():
    start = time.time()
    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.5:
            progress = t / 0.5
            for _ in range(int(progress * 20) + 3):
                y   = random.randint(0, H)
                h   = random.randint(1, 6)
                alp = random.randint(20, 120)
                d.rectangle([0, y, W, y + h], fill=(0, alp, int(alp * 1.8)))
            for _ in range(int(progress * 200)):
                a = random.randint(10, 60)
                d.point((random.randint(0, W), random.randint(0, H)),
                        fill=(0, a, int(a * 1.5)))

        elif t < 1.0:
            progress = (t - 0.5) / 0.5
            ease     = 1 - (1 - progress) ** 3
            band_h   = max(1, int(H * (1 - ease)))
            cy       = H // 2
            top, bot = cy - band_h // 2, cy + band_h // 2
            bright   = int(200 + ease * 55)
            d.rectangle([0, top, W, bot],
                         fill=(0, bright, min(255, int(bright * 1.3))))
            for _ in range(4):
                ny = random.randint(top, max(top, bot - 1))
                d.line([(0, ny), (W, ny)], fill=(0, min(255, bright + 40), 255))

        elif t < 1.3:
            progress = (t - 1.0) / 0.3
            line_w   = max(2, int(W * (1 - progress ** 2)))
            cx, cy   = W // 2, H // 2
            bright   = int(255 * (1 - progress * 0.5))
            d.rectangle([cx - line_w // 2, cy - 1,
                          cx + line_w // 2, cy + 1],
                         fill=(0, bright, min(255, int(bright * 1.3))))

        elif t < 1.8:
            pass

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Glitch resolve intro ───────────────────────────────────────
def _play_intro():
    lines_fonts = _build_fonts()
    layout      = _layout(lines_fonts)
    small       = font(13)
    start       = time.time()

    while True:
        t      = time.time() - start
        img, d = new_frame(bg=BLACK)

        if t < 0.3:
            pass

        elif t < 2.5:
            resolved = ((t - 0.3) / 2.2) ** 0.4
            pulse    = (math.sin(t * 8) + 1) / 2

            for txt, fnt, x, y, th, line_color in layout:
                display = ""
                for i, ch in enumerate(txt):
                    char_r = max(0.0, resolved - (i / len(txt)) * 0.4)
                    display += ch if random.random() < char_r else random.choice(GLITCH_CHARS)

                tw  = fnt.getbbox(display)[2]
                cx  = (W - tw) // 2

                if line_color is not None:
                    col = tuple(int(c * min(1.0, resolved + pulse * 0.15)) for c in line_color)
                else:
                    t_factor = min(1.0, resolved + pulse * 0.15)
                    col = _lerp_color(BASE_COLOR, BRIGHT_COLOR, t_factor)

                d.text((cx + 2, y + 2), display, font=fnt, fill=SHADOW_COLOR)
                d.text((cx, y),         display, font=fnt, fill=col)

                if resolved < 0.9:
                    artifact = "".join(random.choice(GLITCH_CHARS)
                                       for _ in range(random.randint(1, 3)))
                    aa = int((1 - resolved) * 55)
                    gc = tuple(min(255, int(GLITCH_COLOR[i] * (aa / 55))) for i in range(3))
                    d.text((random.randint(10, W - 60),
                            y + random.randint(-10, th)),
                           artifact, font=small, fill=gc)

        else:
            push(img)
            break

        push(img)
        time.sleep(1 / 60)

# ── Idle draw ─────────────────────────────────────────────────
def _draw_idle(d):
    pulse       = (math.sin(time.time() * 2.0) + 1) / 2
    lines_fonts = _build_fonts()
    layout      = _layout(lines_fonts)
    pulse_col   = _lerp_color(BASE_COLOR, BRIGHT_COLOR, pulse)

    for txt, fnt, x, y, th, line_color in layout:
        col = line_color if line_color is not None else pulse_col
        d.text((x + 2, y + 2), txt, font=fnt, fill=SHADOW_COLOR)
        d.text((x, y),         txt, font=fnt, fill=col)

# ── Cleanup ───────────────────────────────────────────────────
def _cleanup(sig=None, frame=None):
    print("\n[icpep] restoring bearbox...")
    _all_off()
    if LED_AVAILABLE:
        lgpio.gpiochip_close(_led_handle)
    for _ in range(15):
        img, d = new_frame(bg=BLACK)
        push(img)
        time.sleep(1 / 30)
    _start_service()
    sys.exit(0)

signal.signal(signal.SIGINT,  _cleanup)
signal.signal(signal.SIGTERM, _cleanup)

# ── Entry ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[icpep] lines:", [(row[0], row[1]) for row in LINES])
    print("[icpep] stopping bearbox...")
    _stop_service()
    time.sleep(0.3)

    _play_shutdown()
    _play_intro()

    # Start LED runner and keyboard listener as background threads
    threading.Thread(target=_led_runner,        daemon=True).start()
    threading.Thread(target=_keyboard_listener, daemon=True).start()

    print("[icpep] running — SPACE cycles LED pattern, Ctrl+C or tap to exit")
    print(f"[icpep] LED pattern → {LED_PATTERN_NAMES[_led_pattern_index]}")

    while True:
        img, d = new_frame(bg=BLACK)
        _draw_idle(d)
        push(img)

        _net_utils._last_tap = 0
        if check_tap():
            _cleanup()

        time.sleep(1 / 30)