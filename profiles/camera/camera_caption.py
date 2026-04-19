#!/usr/bin/env python3
"""
BearBox Camera — Object Detection Captioning

Watches DetectionState for rising-edge motion events.
On each new event (subject to cooldown), grabs the current frame,
runs MobileNet SSD (via OpenCV DNN — no extra dependencies) to detect
objects, and appends a natural description to CaptionLog.

Examples:
  "person detected (92%)"
  "person + cat detected"
  "motion detected — no objects identified"

Flood protection:
  - Rising-edge only (one trigger per motion event, not per frame)
  - Hard cooldown between captions (default 15s, applies to both auto + manual)
  - Single worker — if inference is running, new events are skipped
  - Model loads once on first trigger (~22MB, fast)

Controls (set from camera_stream.py via this module's globals):
  auto_enabled   — bool, enables/disables automatic motion-triggered captioning
  manual_trigger — bool, set True to fire one capture regardless of auto state

Usage (from camera_main.py):
    from camera_caption import CaptionLog, run_captioning
    log = CaptionLog()
    cap_thread = threading.Thread(
        target=run_captioning, args=(state, log), daemon=True
    )
    cap_thread.start()
"""

import cv2
import time
import threading
import base64
import os
from collections import deque

# ── Public control flags (written by camera_stream, read by run_captioning) ──
auto_enabled   = False  # toggle auto motion-triggered captioning (off by default)
manual_trigger = False  # set True to fire one capture immediately

# ── Model paths ───────────────────────────────────────────────
_MODEL_DIR  = os.path.join(os.path.dirname(__file__), "models")
_PROTOTXT   = os.path.join(_MODEL_DIR, "mobilenet_ssd.prototxt")
_CAFFEMODEL = os.path.join(_MODEL_DIR, "mobilenet_ssd.caffemodel")

# MobileNet SSD PASCAL VOC class labels
_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair", "cow",
    "diningtable", "dog", "horse", "motorbike", "person",
    "pottedplant", "sheep", "sofa", "train", "tvmonitor",
]

# Only report these classes — ignore background clutter
_INTERESTING = {
    "person", "cat", "dog", "bird", "cow", "sheep", "horse",
    "car", "bus", "motorbike", "bicycle", "boat", "train",
}

# Minimum confidence to report a detection
_CONFIDENCE = 0.45

# Cooldown between caption jobs in seconds
CAPTION_COOLDOWN = 15.0


# ── Caption Log ───────────────────────────────────────────────

class CaptionLog:
    """
    Thread-safe, fixed-size log of caption entries.
    Each entry: {"timestamp": float, "caption": str, "thumb_b64": str}
    thumb_b64 is a base64-encoded JPEG thumbnail for the Flask log UI.
    """

    MAX_ENTRIES = 20

    def __init__(self):
        self._lock    = threading.Lock()
        self._entries = deque(maxlen=self.MAX_ENTRIES)

    def append(self, caption: str, frame=None):
        """Add a new caption entry. frame is an optional numpy BGR array."""
        thumb_b64 = None
        if frame is not None:
            try:
                thumb = cv2.resize(frame, (160, 90))
                ok, buf = cv2.imencode(
                    ".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60]
                )
                if ok:
                    thumb_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception:
                pass

        entry = {
            "timestamp": time.time(),
            "caption":   caption,
            "thumb_b64": thumb_b64,
        }
        with self._lock:
            self._entries.append(entry)
        print(f"[caption] LOG: {caption}")

    def get_all(self):
        """Return entries newest-first as a plain list (safe copy)."""
        with self._lock:
            return list(reversed(self._entries))

    def clear(self):
        with self._lock:
            self._entries.clear()


# ── Captioning Thread ─────────────────────────────────────────

def run_captioning(state, log: CaptionLog):
    """
    Main caption loop. Runs in its own daemon thread.
    state  — DetectionState instance
    log    — CaptionLog instance
    """
    global manual_trigger

    net         = None   # lazy load
    last_count  = 0
    last_run_ts = 0.0
    busy        = False

    print("[caption] Caption thread started — waiting for trigger...")

    while state.running:
        time.sleep(0.25)

        status      = state.get_status()
        cur_count   = status["motion_count"]
        now         = time.time()
        on_cooldown = (now - last_run_ts) < CAPTION_COOLDOWN

        # ── Check for manual trigger ──────────────────────────
        fired_manual = False
        if manual_trigger:
            manual_trigger = False
            if busy:
                print("[caption] Manual trigger ignored — inference running")
            elif on_cooldown:
                remaining = int(CAPTION_COOLDOWN - (now - last_run_ts))
                print(f"[caption] Manual trigger ignored — cooldown ({remaining}s left)")
                state.caption_status = "COOLDOWN"
            else:
                fired_manual = True
                print("[caption] Manual capture triggered")

        # ── Check for auto motion trigger ─────────────────────
        fired_auto = False
        if not fired_manual and auto_enabled and not busy and not on_cooldown:
            if cur_count != last_count:
                fired_auto = True

        last_count = cur_count

        if not fired_manual and not fired_auto:
            if not busy and not on_cooldown:
                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
            continue

        # ── Fire a caption job ────────────────────────────────
        last_run_ts = now
        busy        = True
        frame       = state.get_frame()
        source      = "MANUAL" if fired_manual else "AUTO"
        state.caption_status = f"CAPTURED ({source})"

        def _infer(frame_copy, trigger_source):
            nonlocal net, busy
            try:
                # ── Lazy model load ───────────────────────────
                if net is None:
                    print("[caption] Loading MobileNet SSD...")
                    state.caption_status = "LOADING MODEL..."
                    if not os.path.isfile(_PROTOTXT) or not os.path.isfile(_CAFFEMODEL):
                        raise FileNotFoundError(
                            f"Model files missing in {_MODEL_DIR}. "
                            "Expected mobilenet_ssd.prototxt and mobilenet_ssd.caffemodel"
                        )
                    net = cv2.dnn.readNetFromCaffe(_PROTOTXT, _CAFFEMODEL)
                    print("[caption] MobileNet SSD loaded")

                # ── Run detection ─────────────────────────────
                state.caption_status = "PROCESSING..."
                caption = _run_detection(net, frame_copy)

                if trigger_source == "MANUAL":
                    caption = f"[manual] {caption}"

                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                state.latest_caption = caption
                log.append(caption, frame_copy)

            except Exception as ex:
                print(f"[caption] Detection error: {ex}")
                state.caption_status = "ERROR"
                log.append(f"[error: {ex}]", frame_copy)
            finally:
                busy = False

        t = threading.Thread(target=_infer, args=(frame, source), daemon=True)
        t.start()

    print("[caption] Caption thread stopped")


def _run_detection(net, frame):
    """
    Run MobileNet SSD on a BGR numpy frame.
    Returns a human-readable string describing what was detected.
    """
    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)),
        0.007843,
        (300, 300),
        127.5
    )
    net.setInput(blob)
    detections = net.forward()

    # Collect confident detections of interesting classes
    found = {}  # label -> best confidence
    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])
        if confidence < _CONFIDENCE:
            continue
        idx   = int(detections[0, 0, i, 1])
        label = _CLASSES[idx] if idx < len(_CLASSES) else "unknown"
        if label not in _INTERESTING:
            continue
        if label not in found or confidence > found[label]:
            found[label] = confidence

    if not found:
        return "motion detected — no objects identified"

    # Build description, highest confidence first
    parts = sorted(found.items(), key=lambda x: -x[1])
    if len(parts) == 1:
        label, conf = parts[0]
        return f"{label} detected ({int(conf * 100)}%)"
    else:
        labels = " + ".join(p[0] for p in parts)
        top_conf = int(parts[0][1] * 100)
        return f"{labels} detected ({top_conf}%)"