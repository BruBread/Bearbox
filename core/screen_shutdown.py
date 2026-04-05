#!/usr/bin/env python3
"""
BearBox — Shutdown Animation
Glitch fade to black. Plays before stopping bearbox service.
"""

import os
import sys
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, font, W, H, get_rotation
from PIL import Image, ImageDraw
import numpy as np

DURATION = 2.5

# Push with the current rotation so animation matches screen orientation
_ROT = get_rotation()

def push(img):
    """Push frame using the saved rotation setting."""
    if _ROT:
        img = img.rotate(_ROT)
    arr    = np.array(img.convert("RGB"), dtype=np.uint16)
    r      = (arr[:, :, 0] >> 3).astype(np.uint16)
    g      = (arr[:, :, 1] >> 2).astype(np.uint16)
    b      = (arr[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    with open("/dev/fb1", "wb") as f:
        f.write(rgb565.tobytes())


def run():
    # Grab current framebuffer content before service releases it
    fb_data = None
    try:
        with open("/dev/fb1", "rb") as f:
            fb_data = f.read(W * H * 2)
    except Exception:
        pass

    F     = font(20, bold=True)
    Fs    = font(13)
    start = time.time()

    while True:
        now      = time.time()
        progress = min((now - start) / DURATION, 1.0)
        if progress >= 1.0:
            break

        # ease in — slow start, fast end
        t = progress * progress

        # Start with black canvas
        img = Image.new("RGB", (W, H), (0, 0, 0))

        # Paste faded version of last screen
        if fb_data:
            try:
                arr  = np.frombuffer(fb_data, dtype=np.uint16).reshape(H, W)
                r    = ((arr >> 11) & 0x1F) << 3
                g    = ((arr >> 5)  & 0x3F) << 2
                b    = (arr & 0x1F) << 3
                rgb  = np.stack([r, g, b], axis=2).astype(np.uint8)
                fade = 1.0 - t
                rgb  = (rgb * fade).astype(np.uint8)
                img.paste(Image.fromarray(rgb, "RGB"), (0, 0))
            except Exception:
                pass

        # Always create a fresh ImageDraw from the current img
        # (never try to re-use the old draw object after paste)
        d = ImageDraw.Draw(img)

        # glitch rectangles
        glitch_count = int(20 * t)
        for _ in range(glitch_count):
            gy  = random.randint(0, H)
            gx  = random.randint(0, W)
            gw  = random.randint(10, max(10, int(200 * t)))
            gh  = random.randint(1, max(1, int(8 * t)))
            v   = int(255 * (1 - t))
            col = (random.randint(0, v), random.randint(0, v), random.randint(0, v))
            d.rectangle([gx, gy, gx + gw, gy + gh], fill=col)

        # horizontal tear lines
        tear_count = int(15 * t)
        for _ in range(tear_count):
            ty  = random.randint(0, H)
            tw  = random.randint(W // 4, W)
            tx  = random.randint(0, W - tw)
            v   = int(180 * (1 - t))
            col = (v, 0, 0)
            d.line([(tx, ty), (tx + tw, ty)], fill=col, width=random.randint(1, 3))

        # BEARBOX OFFLINE text — fades in then out
        if 0.2 < progress < 0.7:
            alpha = min(progress - 0.2, 0.7 - progress) / 0.25
            alpha = max(0.0, min(1.0, alpha))
            a     = int(alpha * 200)
            msg   = "BEARBOX OFFLINE"
            msg2  = "goodbye."
            mw    = F.getbbox(msg)[2]
            mw2   = Fs.getbbox(msg2)[2]
            d.text(((W - mw) // 2,  H // 2 - 20), msg,  font=F,  fill=(a, 0, 0))
            d.text(((W - mw2) // 2, H // 2 + 10), msg2, font=Fs, fill=(int(a * 0.6), 0, 0))

        push(img)
        time.sleep(1 / 30)

    # Final black frame
    img = Image.new("RGB", (W, H), (0, 0, 0))
    push(img)
    time.sleep(0.3)


if __name__ == "__main__":
    run()