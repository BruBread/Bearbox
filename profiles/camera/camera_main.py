#!/usr/bin/env python3
"""
BearBox — Camera Profile Entry Point

Wires together:
  - Intro screen
  - Detection thread (OpenCV motion detection)
  - Overlay thread  (MobileNet SSD box cache, no stream lag)
  - Caption thread  (detect-first + 1.5s presence window)
  - Flask stream thread (MJPEG + log UI)
  - LCD display loop (main thread)

Triggered by profile_manager when a USB camera is detected.
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
        # ── Motion detection ──────────────────────────────────
        "camera_index":   cam.get("camera_index",  0),
        "resolution":     tuple(cam.get("resolution", [640, 480])),
        "threshold":      cam.get("motion_threshold", 500),
        "detect_every":   cam.get("detect_every",  3),
        "blur_size":      cam.get("blur_size",     21),

        # ── Stream ────────────────────────────────────────────
        "stream_port":    cam.get("stream_port",   80),

        # ── Motion confirmation gate ──────────────────────────
        # How many of the last N frames must show motion before
        # the caption thread even runs a detection pass.
        "confirm_window":  cam.get("confirm_window",  5),
        "confirm_hits":    cam.get("confirm_hits",    3),
        "min_motion_area": cam.get("min_motion_area", 2000),

        # ── Presence window ───────────────────────────────────
        # After an object is first detected, it must remain
        # visible for presence_duration seconds to get logged.
        # presence_interval: how often to re-check during window
        # presence_min_hits: checks that must confirm the object
        "presence_duration":  cam.get("presence_duration",  1.5),
        "presence_interval":  cam.get("presence_interval",  0.5),
        "presence_min_hits":  cam.get("presence_min_hits",  2),
    }


def run():
    from profiles.camera.screen_camera_connected import run as play_intro
    play_intro()
    print("[camera] Intro done, loading config...")

    config = _load_camera_config()
    port   = config["stream_port"]

    from profiles.camera.camera_detect import DetectionState, run_detection
    state = DetectionState()

    from profiles.camera.camera_caption import CaptionLog, run_captioning
    log = CaptionLog()

    # Detection thread
    threading.Thread(
        target=run_detection, args=(state, config), daemon=True
    ).start()
    print("[camera] Detection thread started")

    # Overlay thread — inference free-runs, boxes cached for stream
    from profiles.camera.camera_caption import run_overlay
    threading.Thread(
        target=run_overlay, args=(state, config), daemon=True
    ).start()
    print("[camera] Overlay thread started")

    # Caption thread — detect-first + presence window
    threading.Thread(
        target=run_captioning, args=(state, log, config), daemon=True
    ).start()
    print("[camera] Caption thread started")

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