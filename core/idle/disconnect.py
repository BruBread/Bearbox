#!/usr/bin/env python3
"""
BearBox Idle — WiFi Disconnect Screen

Shows current WiFi connection info and provides a "DISCONNECT" button.
When tapped, disconnects from WiFi and shows confirmation.

States:
  connected    — show SSID/IP + "DISCONNECT" button
  disconnecting — running nmcli disconnect command
  disconnected — confirmation screen + "TAP TO RECONNECT" button (optional)
"""



import time, os, sys, math, random, string, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from display import new_frame, push, draw_scanlines, font, C, W, H
import network.net_utils as _net_utils
from network.net_utils import check_tap, tapped

# Reset _last_tap so boot residue doesn't trigger a phantom tap on first draw
_net_utils._last_tap = time.time()

# ── Config ────────────────────────────────────────────────────
IFACE = "wlan0"

# ── Fonts ─────────────────────────────────────────────────────
_F = {}
def _fonts():
    if not _F:
        _F["title"]  = font(28, bold=True)
        _F["big"]    = font(22, bold=True)
        _F["body"]   = font(16, bold=True)
        _F["small"]  = font(13)
        _F["tiny"]   = font(11)
        _F["btn"]    = font(18, bold=True)
    return _F

# ── Background rain ───────────────────────────────────────────
_BG_CHARS    = list(string.ascii_uppercase + string.digits + "!@#$%^&*<>/?|")
_BG_COLS     = []

def _init_bg(F):
    global _BG_COLS
    col_w = W // 14
    _BG_COLS = []
    for i in range(14):
        x = i * col_w + col_w // 2
        _BG_COLS.append({"x": x, "chars": [{
            "char":  random.choice(_BG_CHARS),
            "y":     random.randint(-H, 0) - j * 12,
            "alpha": random.randint(10, 40),
            "speed": random.uniform(0.3, 0.9),
        } for j in range(random.randint(4, 10))]})

def _update_bg():
    for col in _BG_COLS:
        for c in col["chars"]:
            c["y"] += c["speed"]
            if random.random() < 0.04:
                c["char"] = random.choice(_BG_CHARS)
        if all(c["y"] > H for c in col["chars"]):
            y = random.randint(-H // 2, 0)
            col["chars"] = [{
                "char":  random.choice(_BG_CHARS),
                "y":     y - j * 12,
                "alpha": random.randint(10, 40),
                "speed": random.uniform(0.3, 0.9),
            } for j in range(random.randint(4, 10))]

def _draw_bg(d, F):
    for col in _BG_COLS:
        for c in col["chars"]:
            if 0 <= c["y"] <= H:
                a = c["alpha"]
                d.text((col["x"], int(c["y"])), c["char"],
                       font=F["tiny"], fill=(0, a, int(a * 1.5)))

# ── State ─────────────────────────────────────────────────────
_state       = "connected"
_ssid        = None
_ip          = None
_btn_rect    = None
_btn_pressed = 0.0
_bg_inited   = False

def _get_ssid():
    """Get current SSID using iwgetid"""
    try:
        r = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except:
        return None

def _get_ip():
    """Get IP address for wlan0"""
    try:
        r = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
        ips = r.stdout.strip().split()
        return ips[0] if ips else None
    except:
        return None

def _disconnect_thread():
    global _state, _ssid, _ip
    try:
        print(f"[disconnect] disconnecting {IFACE}...")
        r = subprocess.run(
            ["sudo", "nmcli", "device", "disconnect", IFACE],
            capture_output=True, text=True, timeout=10
        )
        print(f"[disconnect] nmcli rc={r.returncode}")
        
        # Wait a moment for interface to actually disconnect
        time.sleep(1)
        
        _ssid = None
        _ip = None
        _state = "disconnected"
        
    except subprocess.TimeoutExpired:
        print("[disconnect] timeout!")
        _state = "connected"  # revert on timeout
    except Exception as e:
        print(f"[disconnect] error: {e}")
        _state = "connected"

def _do_disconnect():
    global _state
    _state = "disconnecting"
    threading.Thread(target=_disconnect_thread, daemon=True).start()

# ── Drawing ───────────────────────────────────────────────────

def _header(d, F):
    d.rectangle([0, 0, W, 40], fill=C["panel"])
    d.line([(0, 40), (W, 40)], fill=C["dimblue"], width=1)
    t  = "BEARBOX NETWORK"
    tw = F["title"].getbbox(t)[2]
    d.text(((W - tw) // 2, 6), t, font=F["title"], fill=C["blue"])

def _info_row(d, F, y, label, value, color):
    d.text((24, y), label, font=F["small"], fill=C["dimwhite"])
    if value:
        vw = F["body"].getbbox(value)[2]
        d.text((W - 24 - vw, y), value, font=F["body"], fill=color)
    else:
        vw = F["small"].getbbox("none")[2]
        d.text((W - 24 - vw, y), "none", font=F["small"], fill=C["dimwhite"])

def _spinner(d, F, y, color):
    s  = ["◐","◓","◑","◒"][int(time.time() * 4) % 4]
    sw = F["big"].getbbox(s)[2]
    d.text(((W - sw) // 2, y), s, font=F["big"], fill=color)

def _btn(d, F, label, y, pulse, color_base=(0, 100, 180)):
    global _btn_rect
    bx, bw, bh = 24, W - 48, 52
    pressed     = time.time() < _btn_pressed
    outline     = C["white"] if pressed else (color_base[0], 
                                               int(color_base[1]+pulse*80), 
                                               int(color_base[2]+pulse*75))
    fill        = (20, 60, 100) if pressed else C["panel"]
    d.rectangle([bx, y, bx+bw, y+bh], fill=fill, outline=outline)
    for sy in range(y+6, y+bh-4, 6):
        d.line([(bx+2, sy), (bx+bw-2, sy)],
               fill=(color_base[0]//4, int((color_base[1]+15+pulse*10)//4), 
                     int((color_base[2]+30+pulse*20)//4)), width=1)
    lw = F["btn"].getbbox(label)[2]
    lh = F["btn"].getbbox(label)[3]
    lx = bx + (bw - lw) // 2
    ly = y  + (bh - lh) // 2
    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        d.text((lx+ox, ly+oy), label, font=F["btn"], fill=(0,20,50))
    d.text((lx, ly), label, font=F["btn"], fill=outline)
    _btn_rect = (bx, y, bw, bh)

def _draw_connected(d, F, pulse):
    global _ssid, _ip
    
    # Refresh network info
    _ssid = _get_ssid()
    _ip = _get_ip()
    
    if _ssid:
        msg = "CONNECTED"
        mw  = F["big"].getbbox(msg)[2]
        d.text(((W-mw)//2, 60), msg, font=F["big"], fill=C["green"])
    else:
        msg = "NOT CONNECTED"
        mw  = F["big"].getbbox(msg)[2]
        d.text(((W-mw)//2, 60), msg, font=F["big"], fill=C["dimwhite"])
    
    _info_row(d, F, 100, "SSID:", _ssid or "—", C["green"] if _ssid else C["dimwhite"])
    _info_row(d, F, 125, "IP:", _ip or "—", C["blue"] if _ip else C["dimwhite"])
    
    d.line([(40, 155), (W-40, 155)], fill=C["dimblue"], width=1)
    
    if _ssid:
        _btn(d, F, "DISCONNECT", 165, pulse, color_base=(180, 80, 0))
    else:
        # No connection, just show inactive button
        hint = "not connected to any network"
        hw = F["small"].getbbox(hint)[2]
        d.text(((W-hw)//2, 180), hint, font=F["small"], fill=C["dimwhite"])

def _draw_disconnecting(d, F):
    _spinner(d, F, 90, C["amber"])
    for txt, y, fnt, col in [
        ("DISCONNECTING...",     130, F["body"],  C["amber"]),
        ("stopping network",     158, F["small"], C["dimwhite"]),
    ]:
        tw = fnt.getbbox(txt)[2]
        d.text(((W-tw)//2, y), txt, font=fnt, fill=col)

def _draw_disconnected(d, F, pulse):
    msg = "DISCONNECTED"
    mw  = F["big"].getbbox(msg)[2]
    d.text(((W-mw)//2, 60), msg, font=F["big"], fill=C["dimwhite"])
    
    sub = "network interface disabled"
    sw  = F["small"].getbbox(sub)[2]
    d.text(((W-sw)//2, 94), sub, font=F["small"], fill=C["dimblue"])
    
    _info_row(d, F, 120, "SSID:", None, C["dimwhite"])
    _info_row(d, F, 145, "IP:", None, C["dimwhite"])

# ── Main draw — called by idle_main 30x/sec ───────────────────
def draw():
    """
    Returns:
      True  — tap outside button, idle_main should cycle screen
      False — tap on button (or busy), idle_main must NOT cycle
    """
    global _bg_inited, _btn_pressed

    F = _fonts()
    if not _bg_inited:
        _init_bg(F)
        _bg_inited = True

    pulse = (math.sin(time.time() * 3) + 1) / 2
    _update_bg()

    # ── Draw ──────────────────────────────────────────────────
    img, d = new_frame(bg=C["bg"])
    draw_scanlines(d)
    _draw_bg(d, F)
    _header(d, F)

    if   _state == "disconnecting": _draw_disconnecting(d, F)
    elif _state == "disconnected":  _draw_disconnected(d, F, pulse)
    else:                           _draw_connected(d, F, pulse)

    if _state != "disconnecting":
        hint = "tap outside button to switch screen"
        hw   = F["tiny"].getbbox(hint)[2]
        d.text(((W-hw)//2, H-14), hint, font=F["tiny"], fill=C["dimblue"])

    push(img)

    # ── Tap — always consume so idle_main never sees our events ──
    if _state == "disconnecting":
        check_tap()   # drain only
        return False

    if check_tap():
        tx, ty = _net_utils._tap_x, _net_utils._tap_y
        print(f"[disconnect] tap ({tx},{ty}) btn={_btn_rect} state={_state}")
        if _btn_rect and tapped(*_btn_rect):
            print("[disconnect] HIT")
            _btn_pressed = time.time() + 0.35
            
            # Only disconnect if we're actually connected
            if _state == "connected" and _get_ssid():
                _do_disconnect()
            return False
        else:
            print("[disconnect] MISS — cycle")
            return True

    return False


if __name__ == "__main__":
    print("Disconnect screen — Ctrl+C to stop")
    while True:
        draw()
        time.sleep(1/30)
