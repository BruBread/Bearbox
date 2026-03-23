#!/usr/bin/env python3
"""
BearBox — Shutdown Animation
Glitch fade to black. Plays before stopping bearbox service.
Call run() then stop the service.
"""

import os
import sys
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, font, W, H

DURATION = 2.5

def run():
    """Play glitch-to-black animation."""
    import subprocess

    # grab current framebuffer content
    try:
        with open("/dev/fb1", "rb") as f:
            fb_data = f.read(W * H * 2)
    except:
        fb_data = None

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

        img, d = new_frame(bg=(0, 0, 0))

        # draw current screen content fading out
        if fb_data:
            try:
                from PIL import Image
                import numpy as np
                arr = np.frombuffer(fb_data, dtype=np.uint16).reshape(H, W)
                r   = ((arr >> 11) & 0x1F) << 3
                g   = ((arr >> 5)  & 0x3F) << 2
                b   = (arr & 0x1F) << 3
                rgb = np.stack([r, g, b], axis=2).astype(np.uint8)
                # darken based on progress
                fade = 1.0 - t
                rgb  = (rgb * fade).astype(np.uint8)
                src  = Image.fromarray(rgb, "RGB")
                img.paste(src, (0, 0))
                d = img._ImageDraw__draw if hasattr(img, '_ImageDraw__draw') else \
                    __import__('PIL.ImageDraw', fromlist=['ImageDraw']).ImageDraw.Draw(img)
            except:
                pass

        # glitch lines
        glitch_count = int(20 * t)
        for _ in range(glitch_count):
            gy  = random.randint(0, H)
            gx  = random.randint(0, W)
            gw  = random.randint(10, int(200 * t))
            gh  = random.randint(1, max(1, int(8 * t)))
            col = (random.randint(0, int(255*(1-t))),
                   random.randint(0, int(255*(1-t))),
                   random.randint(0, int(255*(1-t))))
            d.rectangle([gx, gy, gx+gw, gy+gh], fill=col)

        # horizontal tear lines
        tear_count = int(15 * t)
        for _ in range(tear_count):
            ty  = random.randint(0, H)
            tw  = random.randint(W//4, W)
            tx  = random.randint(0, W - tw)
            col = (random.randint(0, int(180*(1-t))), 0, 0)
            d.line([(tx, ty), (tx+tw, ty)], fill=col, width=random.randint(1, 3))

        # GOODBYE text fades in briefly then out
        if 0.2 < progress < 0.7:
            alpha = min(progress - 0.2, 0.7 - progress) / 0.25
            alpha = max(0.0, min(1.0, alpha))
            a     = int(alpha * 200)
            msg   = "BEARBOX OFFLINE"
            msg2  = "goodbye."
            mw    = F.getbbox(msg)[2]
            mw2   = Fs.getbbox(msg2)[2]
            d.text(((W-mw)//2,  H//2-20), msg,  font=F,  fill=(a, 0, 0))
            d.text(((W-mw2)//2, H//2+10), msg2, font=Fs, fill=(int(a*0.6), 0, 0))

        push(img)
        time.sleep(1/30)

    # final black frame
    img, _ = new_frame(bg=(0, 0, 0))
    push(img)
    time.sleep(0.3)

if __name__ == "__main__":
    run()
