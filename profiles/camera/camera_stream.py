#!/usr/bin/env python3
"""
BearBox Camera — Flask Stream

Minimal MJPEG stream server.
Only serves the raw stream — UI is up to you.

Endpoints:
    GET /stream   — MJPEG stream
    GET /status   — JSON motion status
"""

import cv2
import time
import threading
from flask import Flask, Response, jsonify

app = Flask(__name__)

_state = None   # set by start_stream()


def _generate():
    """Yield MJPEG frames."""
    while True:
        frame = _state.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               buf.tobytes() + b"\r\n")


@app.route("/stream")
def stream():
    return Response(
        _generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    s = _state.get_status()
    return jsonify({
        "motion":       s["motion"],
        "motion_count": s["motion_count"],
        "fps":          s["fps"],
        "last_motion":  s["last_motion"],
    })


def start_stream(state, port=5000):
    """
    Start Flask in a daemon thread.
    Call this once from camera_main.py.
    """
    global _state
    _state = state

    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port,
                               debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    print(f"[stream] Flask running on port {port}")
    return t
