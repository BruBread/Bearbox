#!/usr/bin/env python3
"""
BearBox Camera — AI Sender

Watches for motion, captures a JPEG snapshot, and POSTs it to the
laptop's BearBox server for llava-phi3/Ollama description.
Logs the natural language result back to CaptionLog.

Auto-discovery:
  On startup the sender scans the local /24 subnet for a host responding
  to GET /beacon with {"service": "bearbox-server"}. No IP config needed.
  If laptop_ip is set in config.json it is tried first before scanning.
  If the server disappears mid-session, the sender rescans automatically.

Flow:
  1. Discover laptop server on LAN
  2. Wait for motion confirmation window to pass
  3. Grab raw snapshot (no annotations) → resize to 320x240 → encode JPEG
  4. POST to laptop /describe
  5. Laptop returns natural language description → log it
  6. If laptop unreachable → drop frame, log error, rescan for server
  7. Cooldown starts after send completes

Controls (toggled via camera_stream.py endpoints):
  auto_enabled   — bool, enables motion-triggered sends
  manual_trigger — bool, set True to fire one manual send
"""

import cv2
import time
import base64
import socket
import threading
import ipaddress
import requests
from collections import deque

# ── Public control flags ───────────────────────────────────────
auto_enabled   = False
manual_trigger = False

# ── Constants ──────────────────────────────────────────────────
SEND_COOLDOWN    = 15.0   # seconds between auto sends
BEACON_TIMEOUT   = 0.3    # seconds per host during LAN scan
RESCAN_INTERVAL  = 30.0   # seconds between rescans when server not found
SEND_WIDTH       = 480    # resize frame to this width before sending
SEND_HEIGHT      = 360    # resize frame to this height before sending
SEND_QUALITY     = 60     # JPEG quality for sent frames (lower = faster)


# ── Caption Log ────────────────────────────────────────────────

class CaptionLog:
    MAX_ENTRIES = 20

    def __init__(self):
        self._lock    = threading.Lock()
        self._entries = deque(maxlen=self.MAX_ENTRIES)

    def append(self, description: str, frame=None, tag=None, elapsed=None):
        """
        Add a new log entry.
        description : natural language text from llava-phi3 (or error string)
        frame       : numpy BGR frame to encode as thumbnail (optional)
        tag         : "manual" | "auto" | "error"
        elapsed     : seconds the inference took (float, optional)
        """
        thumb_b64 = None
        if frame is not None:
            try:
                thumb     = cv2.resize(frame, (160, 90))
                ok, buf   = cv2.imencode(
                    ".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60]
                )
                if ok:
                    thumb_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception:
                pass

        entry = {
            "timestamp":   time.time(),
            "description": description,
            "thumb_b64":   thumb_b64,
            "tag":         tag or "auto",
            "elapsed":     elapsed,
        }
        with self._lock:
            self._entries.append(entry)
        print(f"[sender] LOG [{entry['tag']}]: {description}")

    def get_all(self):
        with self._lock:
            return list(reversed(self._entries))

    def clear(self):
        with self._lock:
            self._entries.clear()


# ── LAN discovery ──────────────────────────────────────────────

def _get_local_ip() -> str:
    """Get this device's LAN IP by opening a dummy UDP socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _check_beacon(ip: str, port: int, timeout: float) -> bool:
    """Return True if this host is running the BearBox server beacon."""
    try:
        r = requests.get(
            f"http://{ip}:{port}/beacon",
            timeout=timeout
        )
        return r.ok and r.json().get("service") == "bearbox-server"
    except Exception:
        return False


def _scan_for_server(port: int, hint_ip: str = "") -> str | None:
    """
    Scan the local /24 subnet for a BearBox server.
    Tries hint_ip first if provided (e.g. laptop_ip from config).
    Returns 'http://x.x.x.x:port' or None.
    """
    if hint_ip:
        print(f"[sender] Trying hint IP {hint_ip}...")
        if _check_beacon(hint_ip, port, timeout=1.0):
            print(f"[sender] Found server at hint IP {hint_ip}")
            return f"http://{hint_ip}:{port}"

    local_ip = _get_local_ip()
    subnet   = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    print(f"[sender] Scanning {subnet} for BearBox server on port {port}...")

    for host in subnet.hosts():
        ip = str(host)
        if ip == local_ip:
            continue
        if _check_beacon(ip, port, BEACON_TIMEOUT):
            print(f"[sender] Found server at {ip}")
            return f"http://{ip}:{port}"

    print("[sender] No BearBox server found on LAN")
    return None


# ── HTTP sender ────────────────────────────────────────────────

def _send_frame(frame, laptop_url: str, timeout: int, prompt: str) -> str:
    """
    Resize frame, encode as JPEG, and POST to laptop /describe.
    Sends a small 320x240 frame at quality 60 — fast upload, enough detail.
    Returns description string on success, raises on failure.
    """
    small   = cv2.resize(frame, (SEND_WIDTH, SEND_HEIGHT))
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, SEND_QUALITY])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")

    b64     = base64.b64encode(buf.tobytes()).decode("ascii")
    payload = {
        "image":    b64,
        "prompt":   prompt,
        "metadata": {"source": "bearbox", "timestamp": time.time()},
    }

    resp = requests.post(f"{laptop_url}/describe", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("description", "no description returned")


# ── Sender thread ──────────────────────────────────────────────

def run_sender(state, log: CaptionLog, config: dict):
    """
    Main sender loop. Runs as a daemon thread.

    config keys (all under 'camera' block in config.json):
        laptop_ip         : str   — optional hint IP to try first
        laptop_port       : int   — server port              (default 5000)
        ai_timeout        : int   — HTTP timeout seconds     (default 90)
        ai_prompt         : str   — prompt sent with image   (optional)
        confirm_window    : int   — rolling window size       (default 5)
        confirm_hits      : int   — required motion frames    (default 3)
        min_motion_area   : int   — minimum contour area px² (default 2000)
    """
    global manual_trigger

    hint_ip         = config.get("laptop_ip",      "")
    port            = config.get("laptop_port",    5000)
    timeout         = config.get("ai_timeout",     90)   # bumped for llava-phi3
    prompt          = config.get(
        "ai_prompt",
        "What is happening in this image? One sentence only."
    )
    confirm_window  = config.get("confirm_window",  5)
    confirm_hits    = config.get("confirm_hits",    3)
    min_motion_area = config.get("min_motion_area", 2000)

    print(
        f"[sender] Started — port {port}, "
        f"confirm {confirm_hits}/{confirm_window} frames, "
        f"min area {min_motion_area}px², "
        f"send size {SEND_WIDTH}x{SEND_HEIGHT} q{SEND_QUALITY}"
    )

    # ── Discover server ────────────────────────────────────────
    laptop_url    = None
    last_scan_ts  = 0.0

    def _try_discover():
        nonlocal laptop_url, last_scan_ts
        state.ai_status = "SEARCHING..."
        url = _scan_for_server(port, hint_ip)
        last_scan_ts = time.time()
        if url:
            laptop_url      = url
            state.ai_status = "IDLE" if auto_enabled else "AUTO OFF"
            print(f"[sender] Server locked: {laptop_url}")
        else:
            laptop_url      = None
            state.ai_status = "NO CONNECTION"

    _try_discover()

    motion_history = deque(maxlen=confirm_window)
    last_send_ts   = 0.0
    busy           = False

    while state.running:
        time.sleep(0.25)

        # Rescan if no server and rescan interval elapsed
        if laptop_url is None:
            if time.time() - last_scan_ts >= RESCAN_INTERVAL:
                _try_discover()
            continue

        status      = state.get_status()
        now         = time.time()
        on_cooldown = (now - last_send_ts) < SEND_COOLDOWN

        motion_history.append(status["motion"])
        motion_hits = sum(motion_history)

        # ── Manual trigger ─────────────────────────────────────
        fired_manual = False
        if manual_trigger:
            manual_trigger = False
            if busy:
                print("[sender] Manual trigger ignored — send in progress")
            elif on_cooldown:
                remaining = int(SEND_COOLDOWN - (now - last_send_ts))
                print(f"[sender] Manual trigger ignored — cooldown ({remaining}s left)")
                state.ai_status = "COOLDOWN"
            else:
                fired_manual = True
                print("[sender] Manual send triggered")

        # ── Auto trigger ───────────────────────────────────────
        fired_auto = False
        if (not fired_manual
                and auto_enabled
                and not busy
                and not on_cooldown):

            confirmed = (
                len(motion_history) == confirm_window
                and motion_hits >= confirm_hits
                and status["motion_area"] >= min_motion_area
            )

            if confirmed:
                fired_auto = True
                motion_history.clear()
                time.sleep(2)
                print(
                    f"[sender] Motion confirmed — "
                    f"{motion_hits}/{confirm_window} frames, "
                    f"area={status['motion_area']}px²"
                )

        if not fired_manual and not fired_auto:
            if not busy and not on_cooldown:
                state.ai_status = "IDLE" if auto_enabled else "AUTO OFF"
            continue

        # ── Fire send in worker thread ─────────────────────────
        busy  = True
        frame = state.get_raw_frame()   # clean frame — no red boxes or HUD
        tag   = "manual" if fired_manual else "auto"
        url   = laptop_url

        def _do_send(frame_copy, send_tag, send_url):
            nonlocal busy, last_send_ts, laptop_url

            try:
                state.ai_status = "SENDING..."
                send_start = time.time()
                print(
                    f"[sender] POSTing {SEND_WIDTH}x{SEND_HEIGHT} "
                    f"frame to {send_url}/describe ..."
                )

                description = _send_frame(frame_copy, send_url, timeout, prompt)

                elapsed                  = round(time.time() - send_start, 1)
                last_send_ts             = time.time()
                state.latest_description = description
                state.ai_status          = "IDLE" if auto_enabled else "AUTO OFF"
                print(f"[sender] Done in {elapsed}s")
                log.append(description, frame_copy, tag=send_tag, elapsed=elapsed)

            except requests.exceptions.ConnectionError:
                print(f"[sender] Could not reach {send_url} — will rescan")
                state.ai_status = "NO CONNECTION"
                laptop_url      = None
                last_scan_ts    = 0.0
                log.append("[laptop unreachable — frame dropped]", frame_copy, tag="error")

            except requests.exceptions.Timeout:
                print(f"[sender] Laptop timed out after {timeout}s — dropping")
                state.ai_status = "TIMEOUT"
                log.append("[laptop timed out — frame dropped]", frame_copy, tag="error")

            except Exception as ex:
                print(f"[sender] Unexpected error: {ex}")
                state.ai_status = "ERROR"
                log.append(f"[error: {ex}]", frame_copy, tag="error")

            finally:
                busy = False

        threading.Thread(
            target=_do_send, args=(frame, tag, url), daemon=True
        ).start()

    print("[sender] Sender thread stopped")