#!/usr/bin/env python3
"""
BearBox Offline — WiFi Portal QR Screen

Replaces the old button grid. Shows a red-themed QR code pointing to
bearbox.local so the user can scan it with their phone and configure
wifi through the web portal instead.

Returns True on tap (cycle back to clock) or None (no tap).
"""

import os
import sys
import time
import math

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap

import qrcode
from PIL import Image

PORTAL_URL = "http://bearbox.local"
AP_SSID    = "BearBox-AP"
AP_IP      = "10.0.0.1"

R = {
    "bg":       (12,  0,   0),
    "panel":    (22,  0,   0),
    "red":      (255, 40,  40),
    "midred":   (180, 20,  20),
    "dimred":   (70,  0,   0),
    "darkred":  (25,  0,   0),
    "white":    (255, 220, 220),
    "dimwhite": (140, 80,  80),
}

# ── QR code — generated once, cached ──────────────────────────
_qr_img   = None
_qr_size  = 0

def _make_qr(target_size):
    """
    Build a QR code image with the red-on-dark palette to match
    the offline aesthetic. Returned as a PIL RGBA image.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(PORTAL_URL)
    qr.make(fit=True)

    # dark module = red, light module = near-black background
    img = qr.make_image(
        image_factory=qrcode.image.pil.PilImage,
        fill_color=(220, 30, 30),   # dark modules — red
        back_color=(18,  0,  0),    # light modules — near-black
    ).convert("RGBA")

    # Resize to target, keeping pixel-perfect scaling
    sz  = target_size
    img = img.resize((sz, sz), Image.NEAREST)
    return img

# ── fonts ──────────────────────────────────────────────────────
_F = {}
def _fonts():
    if not _F:
        _F["title"]  = font(18, bold=True)
        _F["body"]   = font(13, bold=True)
        _F["small"]  = font(11)
        _F["tiny"]   = font(10)
    return _F

# ── glitch state ───────────────────────────────────────────────
import random
_glitch_active  = False
_glitch_timer   = 0.0
_glitch_offset  = (0, 0)

def _update_glitch():
    global _glitch_active, _glitch_timer, _glitch_offset
    now = time.time()
    if not _glitch_active:
        if random.random() < 0.015:
            _glitch_active = True
            _glitch_timer  = now
            _glitch_offset = (
                random.randint(-3, 3),
                random.randint(-2, 2),
            )
    else:
        if now - _glitch_timer > random.uniform(0.04, 0.12):
            _glitch_active = False

# ── main draw — called by idle_offline 30x/sec ────────────────
_bg_inited = False
_tick      = 0

def draw():
    """
    Returns True  — tap detected, idle_offline should cycle
            None  — no tap this frame
    """
    global _qr_img, _qr_size, _bg_inited, _tick

    F     = _fonts()
    _tick += 1

    # QR size: square, centered, leaving room for header + footer text
    HEADER_H = 48
    FOOTER_H = 36
    QR_SIZE  = min(W, H - HEADER_H - FOOTER_H) - 16
    QR_SIZE  = (QR_SIZE // 4) * 4  # keep divisible by box_size

    if _qr_img is None or _qr_size != QR_SIZE:
        _qr_img  = _make_qr(QR_SIZE)
        _qr_size = QR_SIZE

    _update_glitch()
    pulse = (math.sin(time.time() * 2.5) + 1) / 2   # 0→1

    img, d = new_frame(bg=R["bg"])

    # scanlines
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(18, 0, 0))

    # occasional glitch scan lines
    if _glitch_active and random.random() < 0.35:
        for _ in range(random.randint(1, 2)):
            gy  = random.randint(0, H)
            gx  = random.randint(0, W // 2)
            gw  = random.randint(15, 80)
            d.line([(gx, gy), (gx + gw, gy)],
                   fill=(random.randint(80, 200), 0, 0), width=1)

    # ── header ────────────────────────────────────────────────
    d.rectangle([0, 0, W, HEADER_H], fill=R["panel"])
    d.line([(0, HEADER_H), (W, HEADER_H)], fill=R["dimred"], width=1)

    title = "WIFI SETUP"
    tw    = F["title"].getbbox(title)[2]
    glow  = (int(120 + pulse * 60), 0, 0)
    for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        d.text(((W - tw) // 2 + ox, 8 + oy), title, font=F["title"], fill=glow)
    d.text(((W - tw) // 2, 8), title, font=F["title"], fill=R["red"])

    sub  = f"connect to  {AP_SSID}  then scan"
    sw   = F["small"].getbbox(sub)[2]
    d.text(((W - sw) // 2, 30), sub, font=F["small"], fill=R["dimwhite"])

    # ── QR code ───────────────────────────────────────────────
    qr_x = (W - QR_SIZE) // 2
    qr_y = HEADER_H + (H - HEADER_H - FOOTER_H - QR_SIZE) // 2

    # glitch offset on the QR block
    ox = _glitch_offset[0] if _glitch_active else 0
    oy = _glitch_offset[1] if _glitch_active else 0

    # thin pulsing border around QR
    border_col = (int(40 + pulse * 50), 0, 0)
    d.rectangle(
        [qr_x - 3 + ox, qr_y - 3 + oy,
         qr_x + QR_SIZE + 3 + ox, qr_y + QR_SIZE + 3 + oy],
        outline=border_col
    )

    img.paste(_qr_img, (qr_x + ox, qr_y + oy))

    # ── footer ────────────────────────────────────────────────
    footer_y = H - FOOTER_H
    d.rectangle([0, footer_y, W, H], fill=R["panel"])
    d.line([(0, footer_y), (W, footer_y)], fill=R["dimred"], width=1)

    url_col = (int(160 + pulse * 95), int(pulse * 20), int(pulse * 20))
    uw = F["body"].getbbox(PORTAL_URL)[2]
    d.text(((W - uw) // 2, footer_y + 5),
           PORTAL_URL, font=F["body"], fill=url_col)

    hint  = "tap to go back"
    hw    = F["tiny"].getbbox(hint)[2]
    d.text(((W - hw) // 2, footer_y + 22),
           hint, font=F["tiny"], fill=R["dimred"])

    push(img)

    # tap → cycle back
    if check_tap():
        return True
    return None


if __name__ == "__main__":
    print("QR screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1 / 30)