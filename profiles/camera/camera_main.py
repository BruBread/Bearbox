#!/usr/bin/env python3
"""
BearBox — Camera Profile Entry Point

Wires together:
  - Intro screen
  - Detection thread  (OpenCV motion detection)
  - Sender thread     (LAN discovery + motion confirmation + POST to laptop)
  - Flask stream thread (MJPEG + log UI)
  - LCD display loop  (main thread)

Triggered by profile_manager when Jieli USB camera (4c4a:4a55) is detected.
Can also be run standalone:
    sudo env PYTHONPATH=/home/bearbox/bearbox/core:/home/bearbox/bearbox \
        python3 camera_main.py
"""

import os
import sys
import threading

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))
sys.path.insert(0, BASE)

from network.net_utils import load_config


def _load_camera_config():
    cfg = load_config()
    cam = cfg.get("camera", {})
    return {
        # ── Camera / motion ───────────────────────────────────
        "camera_index":    cam.get("camera_index",    0),
        "resolution":      tuple(cam.get("resolution", [640, 480])),
        "threshold":       cam.get("motion_threshold", 500),
        "detect_every":    cam.get("detect_every",    3),
        "blur_size":       cam.get("blur_size",       21),

        # ── Stream ────────────────────────────────────────────
        "stream_port":     cam.get("stream_port",     80),

        # ── Motion confirmation ───────────────────────────────
        "confirm_window":  cam.get("confirm_window",  5),
        "confirm_hits":    cam.get("confirm_hits",    3),
        "min_motion_area": cam.get("min_motion_area", 2000),

        # ── Laptop AI server ──────────────────────────────────
        # laptop_ip is optional — used as a hint before LAN scan
        "laptop_ip":       cam.get("laptop_ip",       ""),
        "laptop_port":     cam.get("laptop_port",     5000),
        "ai_timeout":      cam.get("ai_timeout",      30),
        "ai_prompt":       cam.get("ai_prompt",       ""),
    }


def run():
    from profiles.camera.screen_camera_connected import run as play_intro
    play_intro()
    print("[camera] Intro done, loading config...")

    config = _load_camera_config()
    port   = config["stream_port"]

    from profiles.camera.camera_detect import DetectionState, run_detection
    from profiles.camera.camera_sender import CaptionLog, run_sender

    state = DetectionState()
    log   = CaptionLog()

    # Detection thread
    threading.Thread(
        target=run_detection, args=(state, config), daemon=True
    ).start()
    print("[camera] Detection thread started")

    # Sender thread (includes LAN discovery)
    threading.Thread(
        target=run_sender, args=(state, log, config), daemon=True
    ).start()
    print("[camera] Sender thread started")

    # Flask stream thread
    from profiles.camera.camera_stream import start_stream
    start_stream(state, log, port=port)

    # Display loop — main thread, blocks until profile ends
    print("[camera] Starting display loop...")
    from profiles.camera.camera_display import run_display
    try:
        run_display(state, port=port)
    finally:
        state.running = False
        print("[camera] Camera profile stopped")


if __name__ == "__main__":
    run()
