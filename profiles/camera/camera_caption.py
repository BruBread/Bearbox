#!/usr/bin/env python3
"""
BearBox Camera — Object Detection Captioning

Two modes running in parallel:

1. OVERLAY (run_overlay thread) — runs MobileNet SSD on every frame,
   draws labeled bounding boxes directly onto the stream. Controlled
   by overlay_enabled flag. Runs at ~5 FPS to keep CPU reasonable.

2. LOG (run_captioning thread) — on motion trigger (or manual), grabs
   a frame, runs detection, and appends a text description to CaptionLog.
   Controlled by auto_enabled flag with 15s cooldown.

Controls (set from camera_stream.py via this module's globals):
  auto_enabled    — bool, enables auto motion-triggered log entries
  manual_trigger  — bool, set True to fire one manual log entry
  overlay_enabled — bool, enables live object detection boxes on stream

Usage (from camera_main.py):
    from camera_caption import CaptionLog, run_captioning, run_overlay
    log = CaptionLog()
    threading.Thread(target=run_overlay,    args=(state,),     daemon=True).start()
    threading.Thread(target=run_captioning, args=(state, log), daemon=True).start()
"""

import cv2
import time
import threading
import base64
import os
from collections import deque

# ── Public control flags ──────────────────────────────────────
auto_enabled    = False  # auto motion-triggered log entries (off by default)
manual_trigger  = False  # set True to fire one manual log entry
overlay_enabled = False  # live detection boxes on stream (off by default)

# ── Model paths ───────────────────────────────────────────────
_MODEL_DIR  = os.path.join(os.path.dirname(__file__), "models")
_PROTOTXT   = os.path.join(_MODEL_DIR, "mobilenet_ssd.prototxt")
_CAFFEMODEL = os.path.join(_MODEL_DIR, "mobilenet_ssd.caffemodel")

# MobileNet SSD PASCAL VOC labels
_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair", "cow",
    "diningtable", "dog", "horse", "motorbike", "person",
    "pottedplant", "sheep", "sofa", "train", "tvmonitor",
]

_INTERESTING = {
    "person", "cat", "dog", "bird", "cow", "sheep", "horse",
    "car", "bus", "motorbike", "bicycle", "boat", "train",
}

# Colours per class for overlay boxes (BGR)
_COLORS = {
    "person":    (0,   200, 255),   # amber-ish
    "cat":       (0,   255, 180),
    "dog":       (0,   255, 180),
    "bird":      (180, 255,   0),
    "car":       (255, 100,   0),
    "bus":       (255,  80,   0),
    "motorbike": (255, 140,   0),
    "bicycle":   (255, 180,   0),
    "boat":      (200, 200,   0),
    "train":     (255,  60,   0),
    "cow":       (100, 255, 100),
    "sheep":     (100, 255, 100),
    "horse":     (100, 255, 100),
}
_DEFAULT_COLOR = (180, 180, 180)

_CONFIDENCE      = 0.45
CAPTION_COOLDOWN = 15.0

# Shared net — loaded once, used by both overlay and captioning threads
_net_lock = threading.Lock()
_net      = None


def _load_net():
    """Load MobileNet SSD, thread-safe. Returns net or raises."""
    global _net
    with _net_lock:
        if _net is None:
            if not os.path.isfile(_PROTOTXT) or not os.path.isfile(_CAFFEMODEL):
                raise FileNotFoundError(
                    f"Model files missing in {_MODEL_DIR}. "
                    "Expected mobilenet_ssd.prototxt and mobilenet_ssd.caffemodel"
                )
            _net = cv2.dnn.readNetFromCaffe(_PROTOTXT, _CAFFEMODEL)
            print("[caption] MobileNet SSD loaded")
        return _net


# ── Caption Log ───────────────────────────────────────────────

class CaptionLog:
    MAX_ENTRIES = 20

    def __init__(self):
        self._lock    = threading.Lock()
        self._entries = deque(maxlen=self.MAX_ENTRIES)

    def append(self, caption: str, frame=None):
        thumb_b64 = None
        if frame is not None:
            try:
                thumb = cv2.resize(frame, (160, 90))
                ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
                if ok:
                    thumb_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception:
                pass
        entry = {"timestamp": time.time(), "caption": caption, "thumb_b64": thumb_b64}
        with self._lock:
            self._entries.append(entry)
        print(f"[caption] LOG: {caption}")

    def get_all(self):
        with self._lock:
            return list(reversed(self._entries))

    def clear(self):
        with self._lock:
            self._entries.clear()


# ── Overlay Thread ────────────────────────────────────────────

def run_overlay(state):
    """
    Runs MobileNet SSD on every frame and draws labeled boxes onto the
    stream. Polls at ~5 FPS when enabled, idles cheaply when disabled.
    """
    print("[overlay] Overlay thread started")
    net = None

    while state.running:
        if not overlay_enabled:
            time.sleep(0.1)
            continue

        # Lazy load
        if net is None:
            try:
                print("[overlay] Loading MobileNet SSD for overlay...")
                net = _load_net()
            except Exception as e:
                print(f"[overlay] Model load failed: {e}")
                time.sleep(5.0)
                continue

        frame = state.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        try:
            annotated = _annotate_frame(net, frame)
            state.set_overlay_frame(annotated)
        except Exception as e:
            print(f"[overlay] Error: {e}")

        time.sleep(0.2)   # ~5 FPS — light on CPU

    print("[overlay] Overlay thread stopped")


def _annotate_frame(net, frame):
    """Run detection and draw boxes. Returns annotated frame copy."""
    h, w = frame.shape[:2]
    out  = frame.copy()

    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5
    )
    net.setInput(blob)
    detections = net.forward()

    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])
        if confidence < _CONFIDENCE:
            continue
        idx   = int(detections[0, 0, i, 1])
        label = _CLASSES[idx] if idx < len(_CLASSES) else "unknown"
        if label not in _INTERESTING:
            continue

        # Bounding box
        box    = detections[0, 0, i, 3:7] * [w, h, w, h]
        x1, y1, x2, y2 = box.astype(int)
        color  = _COLORS.get(label, _DEFAULT_COLOR)

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Label pill
        tag     = f"{label} {int(confidence * 100)}%"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        pill_y1 = max(y1 - th - 6, 0)
        pill_y2 = max(y1, th + 6)
        cv2.rectangle(out, (x1, pill_y1), (x1 + tw + 6, pill_y2), color, -1)
        cv2.putText(out, tag, (x1 + 3, pill_y2 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    return out


# ── Captioning Thread ─────────────────────────────────────────

def run_captioning(state, log: CaptionLog):
    global manual_trigger

    net         = None
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

        fired_auto = False
        if not fired_manual and auto_enabled and not busy and not on_cooldown:
            if cur_count != last_count:
                fired_auto = True

        last_count = cur_count

        if not fired_manual and not fired_auto:
            if not busy and not on_cooldown:
                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
            continue

        last_run_ts = now
        busy        = True
        frame       = state.get_frame()
        source      = "MANUAL" if fired_manual else "AUTO"
        state.caption_status = f"CAPTURED ({source})"

        def _infer(frame_copy, trigger_source):
            nonlocal net, busy
            try:
                if net is None:
                    state.caption_status = "LOADING MODEL..."
                    net = _load_net()

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

        threading.Thread(target=_infer, args=(frame, source), daemon=True).start()

    print("[caption] Caption thread stopped")


def _run_detection(net, frame):
    """Run MobileNet SSD, return human-readable string."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5
    )
    net.setInput(blob)
    detections = net.forward()

    found = {}
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

    parts = sorted(found.items(), key=lambda x: -x[1])
    if len(parts) == 1:
        label, conf = parts[0]
        return f"{label} detected ({int(conf * 100)}%)"
    labels   = " + ".join(p[0] for p in parts)
    top_conf = int(parts[0][1] * 100)
    return f"{labels} detected ({top_conf}%)"
