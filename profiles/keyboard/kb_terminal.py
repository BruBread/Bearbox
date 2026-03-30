#!/usr/bin/env python3
"""
BearBox Keyboard — Terminal UI
Green terminal that runs shell commands via keyboard input.
Renders output line by line on the 480x320 display.
"""

import os
import sys
import time
import subprocess
import threading
import re

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H
from profiles.keyboard.kb_input import KeyboardReader

# ── Palette ───────────────────────────────────────────────────
P = {
    "bg":       (0,   10,   5),
    "panel":    (0,   20,  10),
    "green":    (0,   255, 100),
    "dimgreen": (0,   140,  60),
    "darkgreen":(0,    40,  20),
    "teal":     (0,   200, 140),
    "dimteal":  (0,    80,  55),
    "white":    (220, 255, 235),
    "dimwhite": (100, 150, 120),
    "red":      (255,  70,  70),
    "yellow":   (220, 255,   0),
    "dim":      (0,    30,  15),
}

# ── Layout ────────────────────────────────────────────────────
HEADER_H      = 34
FOOTER_H      = 22
FONT_SIZE     = 14        # bigger than before (was 12)
LINE_H        = 16        # matches bigger font
SIDE_PAD      = 6
MAX_LINE_W    = W - SIDE_PAD * 2

BODY_TOP      = HEADER_H + 4
BODY_BOT      = H - FOOTER_H - 4
VISIBLE_LINES = (BODY_BOT - BODY_TOP) // LINE_H

PROMPT_SYM  = "$ "
MAX_HISTORY = 50
MAX_OUTPUT  = 200

ALIASES_FILE = f"{BASE}/bashrc_aliases"


def _run_command(cmd_str, cwd):
    """Run a shell command, return (output_lines, new_cwd)."""
    if not cmd_str.strip():
        return [], cwd

    parts = cmd_str.strip().split(None, 1)

    # built-in cd
    if parts[0] == "cd":
        target = parts[1].strip() if len(parts) > 1 else os.path.expanduser("~")
        target = os.path.expanduser(target)
        if not os.path.isabs(target):
            target = os.path.join(cwd, target)
        target = os.path.normpath(target)
        if os.path.isdir(target):
            return [], target
        return [f"cd: {target}: No such file or directory"], cwd

    # built-in clear
    if parts[0] == "clear":
        return ["__CLEAR__"], cwd

    # wrap in bash so aliases and builtins work
    bash_cmd = f'bash --rcfile {ALIASES_FILE} -i -c {repr(cmd_str)}'
    try:
        result = subprocess.run(
            bash_cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            env={
                **os.environ,
                "TERM":    "dumb",
                "COLUMNS": str((W - SIDE_PAD * 2) // 8),
                "LINES":   str(VISIBLE_LINES),
                "HOME":    os.path.expanduser("~"),
                "BASH_ENV": ALIASES_FILE,
            },
        )
        out = result.stdout + result.stderr
        lines = []
        for raw in out.splitlines():
            clean = re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKLMPSTfhilmnsu]', '', raw)
            clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', clean)
            clean = clean.replace('\t', '    ')
            lines.append(clean)
        return lines, cwd
    except subprocess.TimeoutExpired:
        return ["[timeout after 15s]"], cwd
    except Exception as e:
        return [f"[error: {e}]"], cwd


def _wrap_line(text, fnt, max_w):
    if not text:
        return [""]
    chunks = []
    while text:
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fnt.getbbox(text[:mid])[2] <= max_w:
                lo = mid
            else:
                hi = mid - 1
        chunks.append(text[:lo])
        text = text[lo:]
    return chunks


class Terminal:
    def __init__(self):
        self.cwd          = os.path.expanduser("~")
        self.input_buf    = ""
        self.cursor_pos   = 0
        self.scroll_buf   = []
        self.scroll_off   = 0
        self.history      = []
        self.hist_idx     = -1
        self.hist_tmp     = ""
        self._output_lock = threading.Lock()

    def _push_line(self, text, color=None):
        color = color or P["white"]
        with self._output_lock:
            self.scroll_buf.append((text, color))
            if len(self.scroll_buf) > MAX_OUTPUT:
                self.scroll_buf = self.scroll_buf[-MAX_OUTPUT:]

    def submit(self):
        cmd = self.input_buf.strip()
        if cmd and (not self.history or self.history[-1] != cmd):
            self.history.append(cmd)
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
        self.hist_idx = -1
        self.hist_tmp = ""

        prompt_str = f"{self._prompt_text()}{self.input_buf}"
        self._push_line(prompt_str, P["green"])

        self.input_buf  = ""
        self.cursor_pos = 0
        self.scroll_off = 0

        if not cmd:
            return

        if cmd in ("exit", "quit"):
            self._push_line("[unplug keyboard or Ctrl+C to exit]", P["dimgreen"])
            return

        lines, new_cwd = _run_command(cmd, self.cwd)
        self.cwd = new_cwd

        if lines and lines[0] == "__CLEAR__":
            with self._output_lock:
                self.scroll_buf.clear()
            return

        for line in lines:
            self._push_line(line, P["white"])

    def _prompt_text(self):
        try:
            rel = os.path.relpath(self.cwd, os.path.expanduser("~"))
            short = ("~/" + rel if rel != "." else "~") if not rel.startswith("..") else self.cwd
        except Exception:
            short = self.cwd
        if len(short) > 18:
            short = "…" + short[-17:]
        return f"[{short}]{PROMPT_SYM}"

    def handle_key(self, key):
        if key is None:
            return
        if key == "ENTER":
            self.submit()
        elif key == "BACKSPACE":
            if self.cursor_pos > 0:
                self.input_buf  = (self.input_buf[:self.cursor_pos - 1] +
                                   self.input_buf[self.cursor_pos:])
                self.cursor_pos -= 1
        elif key == "DELETE":
            if self.cursor_pos < len(self.input_buf):
                self.input_buf = (self.input_buf[:self.cursor_pos] +
                                  self.input_buf[self.cursor_pos + 1:])
        elif key == "LEFT":
            self.cursor_pos = max(0, self.cursor_pos - 1)
        elif key == "RIGHT":
            self.cursor_pos = min(len(self.input_buf), self.cursor_pos + 1)
        elif key in ("HOME", "CTRL_A"):
            self.cursor_pos = 0
        elif key in ("END", "CTRL_E"):
            self.cursor_pos = len(self.input_buf)
        elif key == "UP":
            if self.history:
                if self.hist_idx == -1:
                    self.hist_tmp = self.input_buf
                    self.hist_idx = len(self.history) - 1
                elif self.hist_idx > 0:
                    self.hist_idx -= 1
                self.input_buf  = self.history[self.hist_idx]
                self.cursor_pos = len(self.input_buf)
        elif key == "DOWN":
            if self.hist_idx != -1:
                if self.hist_idx < len(self.history) - 1:
                    self.hist_idx  += 1
                    self.input_buf  = self.history[self.hist_idx]
                else:
                    self.hist_idx   = -1
                    self.input_buf  = self.hist_tmp
                self.cursor_pos = len(self.input_buf)
        elif key == "PGUP":
            self.scroll_off = min(self.scroll_off + VISIBLE_LINES,
                                  max(0, len(self.scroll_buf) - VISIBLE_LINES))
        elif key == "PGDN":
            self.scroll_off = max(0, self.scroll_off - VISIBLE_LINES)
        elif key == "TAB":
            self._tab_complete()
        elif key == "CTRL_C":
            self._push_line("^C", P["red"])
            self.input_buf  = ""
            self.cursor_pos = 0
            self.hist_idx   = -1
        elif key == "CTRL_L":
            with self._output_lock:
                self.scroll_buf.clear()
            self.scroll_off = 0
        elif key == "CTRL_U":
            self.input_buf  = self.input_buf[self.cursor_pos:]
            self.cursor_pos = 0
        elif key == "CTRL_W":
            buf  = self.input_buf[:self.cursor_pos]
            rest = self.input_buf[self.cursor_pos:]
            buf  = buf.rstrip()
            idx  = buf.rfind(" ")
            buf  = buf[:idx + 1] if idx != -1 else ""
            self.input_buf  = buf + rest
            self.cursor_pos = len(buf)
        elif key == "ESC":
            self.input_buf  = ""
            self.cursor_pos = 0
        elif len(key) == 1:
            self.input_buf = (self.input_buf[:self.cursor_pos] +
                              key +
                              self.input_buf[self.cursor_pos:])
            self.cursor_pos += 1

    def _tab_complete(self):
        buf     = self.input_buf[:self.cursor_pos]
        parts   = buf.split(" ")
        partial = parts[-1]
        try:
            partial_exp = os.path.expanduser(partial)
            if "/" in partial_exp:
                dir_part  = os.path.dirname(partial_exp)
                base_part = os.path.basename(partial_exp)
            else:
                dir_part  = self.cwd
                base_part = partial_exp
            if not os.path.isdir(dir_part):
                return
            matches = [f for f in os.listdir(dir_part) if f.startswith(base_part)]
            if len(matches) == 1:
                match = matches[0]
                full  = os.path.join(dir_part, match) if "/" in partial else match
                if os.path.isdir(os.path.join(dir_part, match)):
                    full += "/"
                parts[-1]       = full
                self.input_buf  = " ".join(parts) + self.input_buf[self.cursor_pos:]
                self.cursor_pos = len(" ".join(parts))
            elif len(matches) > 1:
                self._push_line("  ".join(sorted(matches)[:12]), P["dimgreen"])
        except Exception:
            pass

    def render(self, d, fnt, tick, caps_on):
        # scroll buffer
        wrapped = []
        with self._output_lock:
            buf_copy = list(self.scroll_buf)
        for text, color in buf_copy:
            for chunk in _wrap_line(text, fnt, MAX_LINE_W):
                wrapped.append((chunk, color))

        total   = len(wrapped)
        bottom  = max(0, total - self.scroll_off)
        top     = max(0, bottom - VISIBLE_LINES)
        visible = wrapped[top:bottom]

        for i, (text, color) in enumerate(visible):
            y = BODY_TOP + i * LINE_H
            d.text((SIDE_PAD, y), text, font=fnt, fill=color)

        # prompt + input
        prompt_text = self._prompt_text()
        input_y     = BODY_BOT + 2

        d.text((SIDE_PAD, input_y), prompt_text, font=fnt, fill=P["green"])
        prompt_w = fnt.getbbox(prompt_text)[2]
        before   = self.input_buf[:self.cursor_pos]
        after    = self.input_buf[self.cursor_pos:]
        bw       = fnt.getbbox(before)[2] if before else 0

        d.text((SIDE_PAD + prompt_w, input_y), before, font=fnt, fill=P["white"])

        # blinking cursor
        cur_x = SIDE_PAD + prompt_w + bw
        if tick % 30 < 18:
            char_w = fnt.getbbox(after[0])[2] if after else 7
            d.rectangle([cur_x, input_y, cur_x + char_w, input_y + FONT_SIZE],
                        fill=P["green"])
            if after:
                d.text((cur_x, input_y), after[0], font=fnt, fill=P["bg"])
        if after:
            rest_x = cur_x + (fnt.getbbox(after[0])[2] if after else 0)
            d.text((rest_x, input_y), after[1:], font=fnt, fill=P["white"])

        # scroll indicator
        if self.scroll_off > 0:
            ind = f"↑{self.scroll_off}L"
            iw  = fnt.getbbox(ind)[2]
            d.text((W - iw - SIDE_PAD, BODY_TOP), ind, font=fnt, fill=P["dimteal"])

        # caps lock indicator
        if caps_on:
            cap_label = "CAPS"
            cw = fnt.getbbox(cap_label)[2]
            d.rectangle([W - cw - SIDE_PAD - 4, input_y - 2,
                         W - SIDE_PAD + 2, input_y + FONT_SIZE + 2],
                        fill=P["darkgreen"], outline=P["dimgreen"])
            d.text((W - cw - SIDE_PAD, input_y), cap_label, font=fnt, fill=P["green"])


def run():
    kb   = KeyboardReader()
    term = Terminal()
    Fhdr = font(12, bold=True)
    Fbdy = font(FONT_SIZE)
    tick = 0

    if not kb.start():
        img, d = new_frame(bg=P["bg"])
        msg  = "No keyboard device found"
        msg2 = "Check /dev/input/event*"
        mw   = Fhdr.getbbox(msg)[2]
        mw2  = Fbdy.getbbox(msg2)[2]
        d.text(((W - mw)  // 2, H // 2 - 20), msg,  font=Fhdr, fill=P["red"])
        d.text(((W - mw2) // 2, H // 2 + 10), msg2, font=Fbdy, fill=P["dimgreen"])
        push(img)
        time.sleep(3)
        return

    # welcome
    term._push_line("BearBox Terminal", P["green"])
    term._push_line(
        subprocess.run("uname -r", shell=True,
                       capture_output=True, text=True).stdout.strip(),
        P["dimgreen"]
    )
    term._push_line("bb commands available — Ctrl+L clear", P["dimteal"])
    term._push_line("", P["dim"])

    while True:
        tick += 1

        key = kb.get_char()
        while key is not None:
            term.handle_key(key)
            key = kb.get_char()

        caps_on = kb._caps  # read caps state for indicator

        img, d = new_frame(bg=P["bg"])

        # scanlines
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(0, 8, 4))

        # header
        d.rectangle([0, 0, W, HEADER_H], fill=P["panel"])
        d.line([(0, HEADER_H), (W, HEADER_H)], fill=P["green"], width=1)
        title   = "BEARBOX TERMINAL"
        title_w = Fhdr.getbbox(title)[2]
        d.text(((W - title_w) // 2, 4), title, font=Fhdr, fill=P["green"])

        # cwd
        try:
            rel = os.path.relpath(term.cwd, os.path.expanduser("~"))
            cwd_display = ("~/" + rel if rel != "." else "~") \
                if not rel.startswith("..") else term.cwd
        except Exception:
            cwd_display = term.cwd
        if len(cwd_display) > 28:
            cwd_display = "…" + cwd_display[-27:]
        cw = Fhdr.getbbox(cwd_display)[2]
        d.text((W - cw - SIDE_PAD, 18), cwd_display, font=Fhdr, fill=P["dimgreen"])

        # body separator
        d.line([(0, BODY_BOT), (W, BODY_BOT)], fill=P["dimteal"], width=1)

        # footer
        d.rectangle([0, H - FOOTER_H, W, H], fill=P["panel"])
        d.line([(0, H - FOOTER_H), (W, H - FOOTER_H)], fill=P["dimteal"], width=1)
        hints = "PgUp/Dn: scroll  ↑↓: history  Tab: complete"
        hw    = Fhdr.getbbox(hints)[2]
        d.text(((W - hw) // 2, H - FOOTER_H + 4), hints, font=Fhdr, fill=P["dimteal"])

        term.render(d, Fbdy, tick, caps_on)

        push(img)
        time.sleep(1 / 30)