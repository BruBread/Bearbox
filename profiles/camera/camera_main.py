#!/usr/bin/env python3
"""
BearBox — Camera Profile Entry Point

Wires together:
  - Intro screen
  - Detection thread (OpenCV)
  - Flask stream thread
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

# ── Config ────────────────────────────────────────────────────

def _load_camera_config():
    cfg = load_config()
    cam = cfg.get("camera", {})
    return {
        "camera_index": cam.get("camera_index", 0),
        "resolution":   tuple(cam.get("resolution", [640, 480])),
        "threshold":    cam.get("motion_threshold", 500),
        "detect_every": cam.get("detect_every", 3),
        "blur_size":    cam.get("blur_size", 21),
        "stream_port":  cam.get("stream_port", 5000),
    }

# ── Entry point ───────────────────────────────────────────────

def run():
    # Play intro screen
    from profiles.camera.screen_camera_connected import run as play_intro
    play_intro()

    config = _load_camera_config()
    port   = config["stream_port"]

    # Shared state
    from profiles.camera.camera_detect import DetectionState, run_detection
    state = DetectionState()

    # Start detection thread
    det_thread = threading.Thread(
        target=run_detection,
        args=(state, config),
        daemon=True
    )
    det_thread.start()
    print("[camera] Detection thread started")

    # Start Flask stream thread
    from profiles.camera.camera_stream import start_stream
    start_stream(state, port=port)

    # Run display loop on main thread (blocks until unplugged)
    from profiles.camera.camera_display import run_display
    try:
        run_display(state, port=port)
    finally:
        state.running = False
        print("[camera] Camera profile stopped")


if __name__ == "__main__":
    run()
