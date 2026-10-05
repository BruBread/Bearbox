#!/usr/bin/env python3
"""
BearBox — NEXUS mode

The only thing BearBox does in this build: show the NEXUS booth's live ticket
sales on the LCD.

  1. Connects to the booth Wi-Fi (NexusV, then walawifi).
  2. Finds the NEXUS hub by scanning the /24 for :3000/ping == "nexus-hub".
  3. Opens the hub WebSocket and says hello as a "page" called "bearbox" — this
     registers it in the hub's roster (so the GM panel's BEARBOX light goes
     green) and the hub replies with an "addr" message telling us the signup
     PC's IP.
  4. Polls the signup PC's http://<signup>:4000/api/state for SOLD / TICKETS.

Screens: tap toggles the ticket count and the robot eyes. If we have no live
ticket data (no Wi-Fi, no hub, or the signup server is down) the screen falls
back to a plain red clock — the disconnect screen.
"""

import os
import sys
import time
import json
import threading
import subprocess
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from display import new_frame, push, font, draw_text_centered, C, W, H
from network.net_utils import check_tap
import bear  # the cyan robot eyes
import websocket  # websocket-client

# ── config ────────────────────────────────────────────────────
NETWORKS   = [("NexusV", "aurorawashere"), ("walawifi", "walapassword")]
HUB_CACHE  = os.path.join(BASE, ".nexus_hub")   # last hub IP, tried first next boot
POLL_EVERY = 3        # seconds between signup /api/state polls
STALE_S    = 10       # no fresh ticket data for this long -> red clock

# ── shared state (written by worker threads, read by the draw loop) ──
_lock   = threading.Lock()
_signup = None        # "http://ip:4000" once the hub tells us, else None
_sold   = None        # tickets sold
_cap    = None        # total tickets (cfg.TICKETS)
_fresh  = 0.0         # time.time() of the last good /api/state read


def _set(**kw):
    with _lock:
        g = globals()
        for k, v in kw.items():
            g["_" + k] = v


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


# ── Wi-Fi: keep us on one of the booth networks (nmcli, like bbwifi) ──
def wifi_loop():
    while True:
        ssid = run_cmd("iwgetid -r 2>/dev/null")
        if ssid in (n for n, _ in NETWORKS):
            time.sleep(15)
            continue
        for name, pw in NETWORKS:
            run_cmd(f'sudo nmcli device wifi connect "{name}" password "{pw}" ifname wlan0')
            if run_cmd("iwgetid -r 2>/dev/null") == name:
                break
        time.sleep(15)


# ── find the hub: scan the local /24 for :3000/ping == "nexus-hub" ──
def _my_subnet():
    ip = run_cmd("hostname -I").split()
    for a in ip:
        if a.count(".") == 3 and not a.startswith("127."):
            return a.rsplit(".", 1)[0]
    return "192.168.0"


def _ping_hub(ip, ms=1500):
    try:
        with urllib.request.urlopen(f"http://{ip}:3000/ping", timeout=ms / 1000) as r:
            return ip if r.read(16) == b"nexus-hub" else None
    except Exception:
        return None


def find_hub():
    try:
        saved = open(HUB_CACHE).read().strip()
        if saved and _ping_hub(saved):
            return saved
    except Exception:
        pass
    net = _my_subnet()
    with ThreadPoolExecutor(max_workers=64) as ex:
        for hit in ex.map(lambda i: _ping_hub(f"{net}.{i}"), range(1, 255)):
            if hit:
                try:
                    open(HUB_CACHE, "w").write(hit)
                except Exception:
                    pass
                return hit
    return None


# ── hub WebSocket: register as "bearbox", learn the signup PC's IP ──
def _on_message(ws, raw):
    try:
        m = json.loads(raw)
    except Exception:
        return
    if m.get("t") == "addr":
        ip = m.get("signup") or ws.url.split("/")[2].split(":")[0]  # null = signup on the hub laptop
        _set(signup=f"http://{ip}:4000")


def hub_loop():
    while True:
        ip = find_hub()
        if not ip:
            time.sleep(3)
            continue
        ws = websocket.WebSocketApp(
            f"ws://{ip}:3000/ws",
            on_open=lambda w: w.send(json.dumps({"t": "hello", "id": "bearbox", "role": "page"})),
            on_message=_on_message,
            on_close=lambda w, *a: _set(signup=None),
        )
        ws.run_forever(ping_interval=20, ping_timeout=10)   # returns when the hub drops; rescan
        time.sleep(2)


# ── poll the signup PC for the ticket count ──
def poll_loop():
    while True:
        with _lock:
            base = _signup
        if base:
            try:
                with urllib.request.urlopen(base + "/api/state", timeout=2) as r:
                    st = json.load(r)
                _set(sold=st["sold"], cap=st["cfg"]["TICKETS"], fresh=time.time())
            except Exception:
                pass
        time.sleep(POLL_EVERY)


# ── screens ───────────────────────────────────────────────────
_F = {}


def _fonts():
    if not _F:
        _F["lbl"]   = font(20, bold=True)
        _F["count"] = font(96, bold=True)
        _F["sub"]   = font(18, bold=True)
        _F["clock"] = font(84, bold=True)
        _F["note"]  = font(22, bold=True)
    return _F


def draw_tickets():
    F = _fonts()
    with _lock:
        sold, cap = _sold, _cap
    img, d = new_frame()
    for y in range(0, H, 4):   # scanlines, matching the other screens
        d.line([(0, y), (W, y)], fill=(0, 8, 18))
    draw_text_centered(d, "TICKETS SOLD", F["lbl"], C["blue"], 40)
    draw_text_centered(d, str(sold), F["count"], C["white"], 95)
    draw_text_centered(d, f"of {cap}", F["sub"], C["dimwhite"], 220)
    draw_text_centered(d, f"{cap - sold} LEFT", F["sub"], C["amber"], 250)
    push(img)


def draw_red_clock():
    F = _fonts()
    img, d = new_frame(bg=(12, 0, 0))
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=(40, 0, 0))
    draw_text_centered(d, time.strftime("%H:%M:%S"), F["clock"], C["red"], 100)
    draw_text_centered(d, "NO SIGNAL", F["note"], C["red"], 220)
    push(img)


def online():
    with _lock:
        return _sold is not None and _cap is not None and (time.time() - _fresh) < STALE_S


# ── main ──────────────────────────────────────────────────────
def main():
    for t in (wifi_loop, hub_loop, poll_loop):
        threading.Thread(target=t, daemon=True).start()
    screens = [draw_tickets, bear.draw]
    idx = 0
    while True:
        if online():
            screens[idx]()
            if check_tap():
                idx = (idx + 1) % len(screens)
        else:
            draw_red_clock()
            check_tap()   # drain taps so none queue up while offline
        time.sleep(1 / 30)


if __name__ == "__main__":
    main()
