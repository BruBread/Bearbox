#!/usr/bin/env python3
"""
BearBox Network — On-Screen QWERTY Keyboard
Call run(prompt) to get a string input from the user.
Returns the entered string or None if cancelled.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from display import new_frame, push, draw_scanlines, font, C, W, H
from network.net_utils import fonts, draw_header, check_tap, tapped

# ─────────────────────────────────────────────────────────────
# KEYBOARD LAYOUT
# ─────────────────────────────────────────────────────────────
_ROWS_LOWER = [
    ["q","w","e","r","t","y","u","i","o","p"],
    ["a","s","d","f","g","h","j","k","l"],
    ["SHIFT","z","x","c","v","b","n","m","⌫"],
    ["123","SPACE","DONE","CANCEL"],
]
_ROWS_UPPER = [
    ["Q","W","E","R","T","Y","U","I","O","P"],
    ["A","S","D","F","G","H","J","K","L"],
    ["SHIFT","Z","X","C","V","B","N","M","⌫"],
    ["123","SPACE","DONE","CANCEL"],
]
_ROWS_NUM = [
    ["1","2","3","4","5","6","7","8","9","0"],
    ["-","_","@",".","#","!","?","&","(",")" ],
    ["SHIFT","$","%","^","*","+","=","~","⌫"],
    ["ABC","SPACE","DONE","CANCEL"],
]

# key sizes
_KEY_H   = 42
_KEY_GAD = 4    # gap between keys
_KB_Y    = H - (_KEY_H + _KEY_GAD) * 4 - 8   # keyboard top Y

# ─────────────────────────────────────────────────────────────
# LAYOUT CALCULATOR
# ─────────────────────────────────────────────────────────────

def _calc_row(row, row_y):
    """Calculate key rects for a row. Returns list of (label, x, y, w, h)."""
    keys   = []
    n      = len(row)
    pad    = 4
    total  = W - pad * 2

    # special bottom row with unequal widths
    if row == _ROWS_LOWER[3] or row == _ROWS_UPPER[3] or row == _ROWS_NUM[3]:
        # 123/ABC, SPACE, DONE, CANCEL
        sm_w    = 60
        done_w  = 70
        space_w = total - sm_w * 2 - done_w - _KEY_GAD * 3
        widths  = [sm_w, space_w, done_w, sm_w]
        x = pad
        for i, label in enumerate(row):
            keys.append((label, x, row_y, widths[i], _KEY_H))
            x += widths[i] + _KEY_GAD
        return keys

    key_w = (total - _KEY_GAD * (n - 1)) // n
    x     = pad + (total - (key_w * n + _KEY_GAD * (n - 1))) // 2
    for label in row:
        keys.append((label, x, row_y, key_w, _KEY_H))
        x += key_w + _KEY_GAD
    return keys

def _build_layout(rows):
    """Build full keyboard layout. Returns list of (label, x, y, w, h)."""
    all_keys = []
    for i, row in enumerate(rows):
        row_y = _KB_Y + i * (_KEY_H + _KEY_GAD)
        all_keys.extend(_calc_row(row, row_y))
    return all_keys

# ─────────────────────────────────────────────────────────────
# DRAW
# ─────────────────────────────────────────────────────────────

def _draw_keyboard(d, keys, fnt, pressed_label=None):
    for label, x, y, w, h in keys:
        is_special = label in ("SHIFT","⌫","DONE","CANCEL","SPACE","123","ABC")
        is_action  = label in ("DONE",)
        is_cancel  = label in ("CANCEL",)
        is_pressed = label == pressed_label

        if is_pressed:
            bg  = C["blue"]
            fg  = C["white"]
            out = C["blue"]
        elif is_action:
            bg  = (0, 40, 20)
            fg  = C["green"]
            out = C["green"]
        elif is_cancel:
            bg  = (30, 0, 0)
            fg  = C["red"]
            out = C["red"]
        elif is_special:
            bg  = (20, 30, 45)
            fg  = C["dimwhite"]
            out = C["dimblue"]
        else:
            bg  = C["panel"]
            fg  = C["white"]
            out = C["dimblue"]

        d.rectangle([x, y, x+w, y+h], fill=bg, outline=out)

        # label — shrink font for wide labels
        if label == "SPACE":
            display_label = "SPACE"
            lw = fnt.getbbox(display_label)[2]
            d.text((x + (w - lw) // 2, y + (h - 14) // 2),
                   display_label, font=font(11), fill=fg)
        else:
            lw = fnt.getbbox(label)[2]
            lh = fnt.getbbox(label)[3]
            d.text((x + (w - lw) // 2, y + (h - lh) // 2),
                   label, font=fnt, fill=fg)

def _draw_input(d, F, prompt, text, show_pw):
    """Draw the input field at top."""
    # background panel
    d.rectangle([0, 0, W, _KB_Y - 2], fill=C["panel"])
    d.line([(0, _KB_Y - 2), (W, _KB_Y - 2)], fill=C["dimblue"], width=1)

    # prompt
    pw = F["small"].getbbox(prompt)[2]
    d.text(((W - pw) // 2, 8), prompt, font=F["small"], fill=C["dimwhite"])

    # input box
    box_x, box_y = 10, 26
    box_w, box_h = W - 20, 32
    d.rectangle([box_x, box_y, box_x+box_w, box_y+box_h],
                fill=(5, 10, 20), outline=C["blue"])

    # text or masked
    display = ("*" * len(text)) if show_pw else text
    # truncate from left if too long
    while F["body"].getbbox(display)[2] > box_w - 16 and display:
        display = display[1:]

    d.text((box_x + 8, box_y + 7), display, font=F["body"], fill=C["white"])

    # blinking cursor
    if int(time.time() * 2) % 2 == 0:
        cur_x = box_x + 8 + F["body"].getbbox(display)[2] + 2
        d.rectangle([cur_x, box_y + 6, cur_x + 4, box_y + 24],
                    fill=C["blue"])

    # show/hide password hint
    hint = "TAP EYE TO SHOW" if show_pw else ""
    if hint:
        hw = F["small"].getbbox(hint)[2]
        d.text(((W - hw) // 2, box_y + box_h + 4),
               hint, font=F["small"], fill=C["dimblue"])

    # eye toggle button
    eye_label = "HIDE" if not show_pw else "SHOW"
    eye_x     = W - 52
    eye_y     = box_y + 4
    eye_w     = 44
    eye_h     = 24
    d.rectangle([eye_x, eye_y, eye_x+eye_w, eye_y+eye_h],
                fill=C["panel"], outline=C["dimblue"])
    ew = F["small"].getbbox(eye_label)[2]
    d.text((eye_x + (eye_w - ew) // 2, eye_y + 5),
           eye_label, font=F["small"], fill=C["dimwhite"])

    return (eye_x, eye_y, eye_w, eye_h)   # eye rect

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run(prompt="Enter Password", mask=True):
    """
    Show on-screen keyboard.
    prompt: label shown above input box
    mask:   if True, shows asterisks
    Returns entered string or None if cancelled.
    """
    F        = fonts()
    key_fnt  = font(13, bold=True)

    text     = ""
    shifted  = False
    num_mode = False
    show_pw  = not mask   # show_pw=True means show actual chars

    while True:
        # pick layout
        if num_mode:
            rows = _ROWS_NUM
        elif shifted:
            rows = _ROWS_UPPER
        else:
            rows = _ROWS_LOWER

        keys = _build_layout(rows)

        img, d = new_frame()
        draw_scanlines(d)

        eye_rect = _draw_input(d, F, prompt, text, mask and not show_pw)
        _draw_keyboard(d, keys, key_fnt)

        push(img)

        if check_tap():
            # check eye toggle
            if tapped(*eye_rect):
                show_pw = not show_pw
                continue

            # check keyboard keys
            for label, x, y, w, h in keys:
                if tapped(x, y, w, h):
                    if label == "⌫":
                        text = text[:-1]
                    elif label == "SPACE":
                        text += " "
                    elif label == "SHIFT":
                        shifted = not shifted
                    elif label in ("123", "ABC"):
                        num_mode = not num_mode
                        shifted  = False
                    elif label == "DONE":
                        return text
                    elif label == "CANCEL":
                        return None
                    else:
                        text   += label
                        shifted = False   # auto-unshift after typing
                    break

        time.sleep(1 / 30)
