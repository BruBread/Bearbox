#!/usr/bin/env python3
"""
BearBox Keyboard — Terminal UI
Pink terminal that runs shell commands via keyboard input.
Renders output line by line on the 480x320 display.
"""

import os
import sys
import time
import subprocess
import threading
import shlex

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, W, H
from profiles.keyboard.kb_input import KeyboardReader

# ── Palette ───────────────────────────────────────────────────
P = {
    "bg":       (8,   0,  18),
    "panel":    (18,  5,  35),
    "magenta":  (255, 0,  180),
    "pink":     (220, 80, 200),
    "dimpink":  (100, 20, 90),
    "purple":   (140, 0,  200),
    "dimpurple":(40,  0,  60),
    "white":    (240, 220, 255),
    "dimwhite": (120, 100, 140),
    "green":    (0,   255, 140),
    "red":      (255, 50,  80),
    "yellow":   (255, 220, 0),
    "dim":      (30,  10,  45),
}

# ── Layout ────────────────────────────────────────────────────
HEADER_H    = 32       # top bar height
FOOTER_H    = 20       # bottom bar height
LINE_H      = 14       # pixels per terminal line
FONT_SIZE   = 12
SIDE_PAD    = 6        # left/right padding
MAX_LINE_W  = W - SIDE_PAD * 2

BODY_TOP    = HEADER_H + 4
BODY_BOT    = H - FOOTER_H - 4
VISIBLE_LINES = (BODY_BOT - BODY_TOP) // LINE_H   # how many lines fit

PROMPT_SYM  = "$ "
MAX_HISTORY = 50       # command history size
MAX_OUTPUT  = 200      # max lines kept in scroll buffer


def _run_command(cmd_str, cwd):
    """Run a shell command, return (output_lines, new_cwd)."""
    if not cmd_str.strip():
        return [], cwd

    # built-in cd
    parts = cmd_str.strip().split(None, 1)
    if parts[0] == "cd":
        target = parts[1].strip() if len(parts) > 1 else os.path.expanduser("~")
        target = os.path.expanduser(target)
        if not os.path.isabs(target):
            target = os.path.join(cwd, target)
        target = os.path.normpath(target)
        if os.path.isdir(target):
            return [], target
        else:
            return [f"cd: {target}: No such file or directory"], cwd

    # built-in clear
    if parts[0] == "clear":
        return ["__CLEAR__"], cwd

    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "54", "LINES": "17"},
        )
        out = result.stdout + result.stderr
        lines = []
        for raw_line in out.splitlines():
            # strip ANSI escape codes
            import re
            clean = re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKLMPSTfhilmnsu]', '', raw_line)
            clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', clean)
            clean = clean.replace('\t', '    ')
            if clean or raw_line:
                lines.append(clean)
        return lines, cwd
    except subprocess.TimeoutExpired:
        return ["[timeout after 15s]"], cwd
    except Exception as e:
        return [f"[error: {e}]"], cwd


def _wrap_line(text, fnt, max_w):
    """Wrap a single string into display-width chunks."""
    if not text:
        return [""]
    chunks = []
    while text:
        # binary search for max chars that fit
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
        self.input_buf    = ""       # current typed line
        self.cursor_pos   = 0        # cursor within input_buf
        self.scroll_buf   = []       # list of (text, color) tuples
        self.scroll_off   = 0        # lines scrolled up from bottom
        self.history      = []       # command history
        self.hist_idx     = -1       # -1 = not browsing
        self.hist_tmp     = ""       # saved current input when browsing
        self._output_lock = threading.Lock()

    def _push_line(self, text, color=None):
        color = color or P["white"]
        with self._output_lock:
            self.scroll_buf.append((text, color))
            if len(self.scroll_buf) > MAX_OUTPUT:
                self.scroll_buf = self.scroll_buf[-MAX_OUTPUT:]
            # auto-scroll to bottom unless user scrolled up
            if self.scroll_off == 0:
                pass  # already at bottom

    def submit(self):
        cmd = self.input_buf.strip()

        # add to history
        if cmd and (not self.history or self.history[-1] != cmd):
            self.history.append(cmd)
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
        self.hist_idx = -1
        self.hist_tmp = ""

        # echo the command
        prompt_str = f"{self._prompt_text()}{self.input_buf}"
        self._push_line(prompt_str, P["magenta"])

        self.input_buf = ""
        self.cursor_pos = 0
        self.scroll_off = 0  # snap to bottom on submit

        if not cmd:
            return

        if cmd in ("exit", "quit"):
            self._push_line("[use Ctrl+C or unplug keyboard to exit]", P["dimpink"])
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
        # shorten cwd: ~/some/path
        try:
            rel = os.path.relpath(self.cwd, os.path.expanduser("~"))
            if rel.startswith(".."):
                short = self.cwd
            else:
                short = "~/" + rel if rel != "." else "~"
        except:
            short = self.cwd
        # cap length
        if len(short) > 20:
            short = "…" + short[-19:]
        return f"[bb {short}]{PROMPT_SYM}"

    def handle_key(self, key):
        if key is None:
            return

        if key == "ENTER":
            self.submit()

        elif key == "BACKSPACE":
            if self.cursor_pos > 0:
                self.input_buf = (self.input_buf[:self.cursor_pos - 1] +
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

        elif key == "HOME" or key == "CTRL_A":
            self.cursor_pos = 0

        elif key == "END" or key == "CTRL_E":
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
            # basic tab completion
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
            # delete word before cursor
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
        """Simple path/command tab completion."""
        buf = self.input_buf[:self.cursor_pos]
        parts = buf.split(" ")
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

            matches = [
                f for f in os.listdir(dir_part)
                if f.startswith(base_part)
            ]

            if len(matches) == 1:
                match = matches[0]
                full  = os.path.join(dir_part, match) if "/" in partial else match
                if os.path.isdir(os.path.join(dir_part, match)):
                    full += "/"
                # replace partial in buf
                parts[-1]       = full
                self.input_buf  = " ".join(parts) + self.input_buf[self.cursor_pos:]
                self.cursor_pos = len(" ".join(parts))

            elif len(matches) > 1:
                # show options
                self._push_line("  ".join(sorted(matches)[:12]), P["dimpink"])

        except:
            pass

    def render(self, d, fnt, tick):
        """Draw the terminal body onto an existing draw context."""
        # ── scroll buffer ─────────────────────────────────────
        # expand all lines through word-wrap
        wrapped = []
        with self._output_lock:
            buf_copy = list(self.scroll_buf)

        for text, color in buf_copy:
            for chunk in _wrap_line(text, fnt, MAX_LINE_W):
                wrapped.append((chunk, color))

        # determine which lines to show
        total  = len(wrapped)
        bottom = max(0, total - self.scroll_off)
        top    = max(0, bottom - VISIBLE_LINES)
        visible = wrapped[top:bottom]

        # draw lines
        for i, (text, color) in enumerate(visible):
            y = BODY_TOP + i * LINE_H
            d.text((SIDE_PAD, y), text, font=fnt, fill=color)

        # ── prompt + input line ───────────────────────────────
        prompt_text = self._prompt_text()
        input_y     = BODY_BOT + 2

        d.text((SIDE_PAD, input_y), prompt_text, font=fnt, fill=P["magenta"])

        prompt_w = fnt.getbbox(prompt_text)[2]
        before   = self.input_buf[:self.cursor_pos]
        after    = self.input_buf[self.cursor_pos:]
        bw       = fnt.getbbox(before)[2] if before else 0

        d.text((SIDE_PAD + prompt_w, input_y), before, font=fnt, fill=P["white"])

        # cursor block (blinks)
        cur_x = SIDE_PAD + prompt_w + bw
        if tick % 30 < 18:
            char_w = fnt.getbbox(self.input_buf[self.cursor_pos])[2] if after else 7
            d.rectangle([cur_x, input_y, cur_x + char_w, input_y + FONT_SIZE],
                        fill=P["magenta"])
            if after:
                d.text((cur_x, input_y), after[0], font=fnt, fill=P["bg"])

        if after:
            rest_x = cur_x + (fnt.getbbox(after[0])[2] if after else 0)
            d.text((rest_x, input_y), after[1:], font=fnt, fill=P["white"])

        # scroll indicator
        if self.scroll_off > 0:
            ind = f"↑ {self.scroll_off}L"
            iw  = fnt.getbbox(ind)[2]
            d.text((W - iw - SIDE_PAD, BODY_TOP), ind, font=fnt, fill=P["dimpurple"])


def run():
    kb   = KeyboardReader()
    term = Terminal()
    Fhdr = font(11, bold=True)
    Fbdy = font(FONT_SIZE)
    tick = 0

    if not kb.start():
        # show error on screen then return
        img, d = new_frame(bg=P["bg"])
        msg  = "No keyboard device found"
        msg2 = "Check /dev/input/event*"
        mw   = Fhdr.getbbox(msg)[2]
        mw2  = Fbdy.getbbox(msg2)[2]
        d.text(((W - mw)  // 2, H // 2 - 20), msg,  font=Fhdr, fill=P["red"])
        d.text(((W - mw2) // 2, H // 2 + 10), msg2, font=Fbdy, fill=P["dimpink"])
        push(img)
        time.sleep(3)
        return

    # welcome message
    term._push_line("BearBox Terminal", P["magenta"])
    term._push_line(f"kernel: {subprocess.run('uname -r', shell=True, capture_output=True, text=True).stdout.strip()}", P["dimpink"])
    term._push_line("type 'help' for shell help, Ctrl+L to clear", P["dimpink"])
    term._push_line("", P["dim"])

    while True:
        tick += 1

        # process keyboard input
        key = kb.get_char()
        while key is not None:
            term.handle_key(key)
            key = kb.get_char()

        # draw frame
        img, d = new_frame(bg=P["bg"])

        # scanlines
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(8, 0, 18))

        # header bar
        d.rectangle([0, 0, W, HEADER_H], fill=P["panel"])
        d.line([(0, HEADER_H), (W, HEADER_H)], fill=P["magenta"], width=1)
        title    = "BEARBOX TERMINAL"
        title_w  = Fhdr.getbbox(title)[2]
        d.text(((W - title_w) // 2, 4), title, font=Fhdr, fill=P["magenta"])

        # cwd in header
        try:
            rel = os.path.relpath(term.cwd, os.path.expanduser("~"))
            cwd_display = ("~/" + rel if rel != "." else "~") if not rel.startswith("..") else term.cwd
        except:
            cwd_display = term.cwd
        if len(cwd_display) > 30:
            cwd_display = "…" + cwd_display[-29:]
        cw = Fhdr.getbbox(cwd_display)[2]
        d.text((W - cw - SIDE_PAD, 18), cwd_display, font=Fhdr, fill=P["dimpink"])

        # separator above input
        d.line([(0, BODY_BOT), (W, BODY_BOT)], fill=P["dimpurple"], width=1)

        # footer
        d.rectangle([0, H - FOOTER_H, W, H], fill=P["panel"])
        d.line([(0, H - FOOTER_H), (W, H - FOOTER_H)], fill=P["dimpurple"], width=1)
        hints = "PgUp/Dn: scroll  ↑↓: history  Tab: complete  Ctrl+L: clear"
        hw    = Fhdr.getbbox(hints)[2]
        d.text(((W - hw) // 2, H - FOOTER_H + 5), hints, font=Fhdr, fill=P["dimpurple"])

        # terminal body
        term.render(d, Fbdy, tick)

        push(img)
        time.sleep(1 / 30)
