#!/usr/bin/env python3
"""
BearBox Camera — Object Detection Captioning

Two modes running in parallel:

1. OVERLAY (run_overlay thread) — runs MobileNet SSD as fast as inference
   allows (no fixed sleep — Pi 4 naturally rate-limits at ~3-5 FPS on CPU).
   Writes a box list to state via set_overlay_boxes(); get_stream_frame()
   redraws those boxes onto every fresh camera frame at full camera FPS.
   No more lag from waiting on inference before serving a stream frame.

2. LOG (run_captioning thread) — triggers on confirmed motion or manual
   request, appends a text description to CaptionLog with 15s cooldown.

Motion confirmation (auto mode):
   Requires motion to be present in at least CONFIRM_HITS out of the last
   CONFIRM_WINDOW frames AND total motion_area >= MIN_MOTION_AREA before
   firing a caption. Filters single-frame flickers, lighting changes, and
   noise that just barely clears the contour threshold.

Controls (set from camera_stream.py via this module's globals):
  auto_enabled    — bool, enables auto motion-triggered log entries
  manual_trigger  — bool, set True to fire one manual log entry
  overlay_enabled — bool, enables live object detection boxes on stream

Config keys (passed in from camera_main.py via config dict):
  confirm_window   : int   — rolling window size        (default 5)
  confirm_hits     : int   — required motion frames     (default 3)
  min_motion_area  : int   — minimum total contour px²  (default 2000)

Usage (from camera_main.py):
    from camera_caption import CaptionLog, run_captioning, run_overlay
    log = CaptionLog()
    threading.Thread(target=run_overlay,    args=(state, config), daemon=True).start()
    threading.Thread(target=run_captioning, args=(state, log, config), daemon=True).start()
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

def run_overlay(state, config=None):
    """
    Runs MobileNet SSD as fast as inference allows and stores the resulting
    box list in state via set_overlay_boxes(). get_stream_frame() redraws
    those boxes onto every fresh camera frame, so the MJPEG feed always
    runs at full camera FPS regardless of inference speed.

    When overlay is disabled the thread idles cheaply and clears the box
    cache so no stale boxes appear if overlay is re-enabled later.
    """
    print("[overlay] Overlay thread started")
    net = None

    while state.running:
        if not overlay_enabled:
            # Clear stale boxes so they don't reappear on re-enable
            state.set_overlay_boxes([], False)
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
            boxes = _detect_boxes(net, frame)
            # Push box list — stream thread redraws at full FPS from cache
            state.set_overlay_boxes(boxes, overlay_enabled)
        except Exception as e:
            print(f"[overlay] Error: {e}")

        # No sleep here — inference time is the natural rate limiter.
        # On Pi 4 CPU this lands at ~3-5 FPS which is fine for overlay.

    print("[overlay] Overlay thread stopped")


def _detect_boxes(net, frame):
    """
    Run MobileNet SSD, return list of box tuples.
    Each tuple: (x1, y1, x2, y2, label, confidence)
    """
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5
    )
    net.setInput(blob)
    detections = net.forward()

    boxes = []
    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])
        if confidence < _CONFIDENCE:
            continue
        idx   = int(detections[0, 0, i, 1])
        label = _CLASSES[idx] if idx < len(_CLASSES) else "unknown"
        if label not in _INTERESTING:
            continue

        box = detections[0, 0, i, 3:7] * [w, h, w, h]
        x1, y1, x2, y2 = box.astype(int)
        boxes.append((x1, y1, x2, y2, label, confidence))

    return boxes


# ── Captioning Thread ─────────────────────────────────────────

def run_captioning(state, log: CaptionLog, config=None):
    """
    Watches for confirmed motion or manual trigger and appends
    detection descriptions to the CaptionLog.

    Motion confirmation:
      Keeps a rolling deque of the last CONFIRM_WINDOW motion booleans.
      Only fires when >= CONFIRM_HITS of those frames show motion AND
      the current motion_area >= MIN_MOTION_AREA. This prevents single-
      frame noise, flicker, and tiny pixel-level changes from triggering.
    """
    global manual_trigger

    cfg              = config or {}
    confirm_window   = cfg.get("confirm_window",  5)
    confirm_hits     = cfg.get("confirm_hits",    3)
    min_motion_area  = cfg.get("min_motion_area", 2000)

    net              = None
    last_run_ts      = 0.0
    busy             = False

    # Rolling motion history for confirmation window
    motion_history   = deque(maxlen=confirm_window)

    print(
        f"[caption] Caption thread started "
        f"(confirm {confirm_hits}/{confirm_window} frames, "
        f"min area {min_motion_area}px²)"
    )

    while state.running:
        time.sleep(0.25)

        status      = state.get_status()
        now         = time.time()
        on_cooldown = (now - last_run_ts) < CAPTION_COOLDOWN

        # Update rolling motion history
        motion_history.append(status["motion"])
        motion_hits = sum(motion_history)

        # ── Manual trigger ────────────────────────────────────
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

        # ── Auto trigger — confirmation window + area gate ────
        fired_auto = False
        if (not fired_manual
                and auto_enabled
                and not busy
                and not on_cooldown):

            confirmed = (
                len(motion_history) == confirm_window          # window full
                and motion_hits >= confirm_hits                 # enough motion frames
                and status["motion_area"] >= min_motion_area   # area large enough
            )

            if confirmed:
                fired_auto = True
                print(
                    f"[caption] Auto trigger — "
                    f"{motion_hits}/{confirm_window} frames, "
                    f"area={status['motion_area']}px²"
                )
                # Clear history so we don't immediately re-trigger
                motion_history.clear()

        # ── Update status display ─────────────────────────────
        if not fired_manual and not fired_auto:
            if not busy and not on_cooldown:
                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
            continue

        # ── Fire inference ────────────────────────────────────
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
    boxes = _detect_boxes(net, frame)

    if not boxes:
        return "motion detected — no objects identified"

    # Collapse duplicates, keep highest confidence per label
    found = {}
    for (_, _, _, _, label, conf) in boxes:
        if label not in found or conf > found[label]:
            found[label] = conf

    parts = sorted(found.items(), key=lambda x: -x[1])
    if len(parts) == 1:
        label, conf = parts[0]
        return f"{label} detected ({int(conf * 100)}%)"

    labels   = " + ".join(p[0] for p in parts)
    top_conf = int(parts[0][1] * 100)
    return f"{labels} detected ({top_conf}%)"
