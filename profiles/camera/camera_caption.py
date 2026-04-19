#!/usr/bin/env python3
"""
BearBox Camera — Object Detection Captioning

Two modes running in parallel:

1. OVERLAY (run_overlay thread) — runs MobileNet SSD as fast as inference
   allows, writes box list to state via set_overlay_boxes(). Stream redraws
   boxes at full camera FPS from cache — no inference-gated lag.

2. LOG (run_captioning thread) — new detect-first flow:

   OLD flow: motion confirmed → grab frame → log
   NEW flow:
     a) Motion confirmation window passes
     b) Quick detection pass — if nothing interesting, silently drop + reset
     c) Something detected → start 1.5s presence watch
     d) Run detection every 0.5s during watch window
     e) Object must appear in >= 2 of 3 check passes (consistency gate)
     f) Still present at end of window → log it
     g) Disappeared before window ends → drop, no log
     h) Cooldown starts AFTER watch window completes (not on first motion)

   This means:
     - Frame noise / lighting changes → dropped at step (b)
     - Something walks past quickly → dropped at step (g)
     - Something lingers at your door → logged at step (f)

Controls (set from camera_stream.py via this module's globals):
  auto_enabled    — bool, enables auto motion-triggered log entries
  manual_trigger  — bool, set True to fire one manual log entry
  overlay_enabled — bool, enables live object detection boxes on stream

Config keys (from config.json camera block):
  confirm_window      : int   — motion rolling window size       (default 5)
  confirm_hits        : int   — required motion frames           (default 3)
  min_motion_area     : int   — minimum contour area px²         (default 2000)
  presence_duration   : float — seconds object must persist      (default 1.5)
  presence_interval   : float — seconds between presence checks  (default 0.5)
  presence_min_hits   : int   — checks that must confirm object  (default 2)
"""

import cv2
import time
import threading
import base64
import os
from collections import deque

# ── Public control flags ──────────────────────────────────────
auto_enabled    = False
manual_trigger  = False
overlay_enabled = False

# ── Model paths ───────────────────────────────────────────────
_MODEL_DIR  = os.path.join(os.path.dirname(__file__), "models")
_PROTOTXT   = os.path.join(_MODEL_DIR, "mobilenet_ssd.prototxt")
_CAFFEMODEL = os.path.join(_MODEL_DIR, "mobilenet_ssd.caffemodel")

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

_net_lock = threading.Lock()
_net      = None


def _load_net():
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
    box list in state via set_overlay_boxes(). Stream redraws those boxes
    at full camera FPS — never blocks on inference.
    """
    print("[overlay] Overlay thread started")
    net = None

    while state.running:
        if not overlay_enabled:
            state.set_overlay_boxes([], False)
            time.sleep(0.1)
            continue

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
            state.set_overlay_boxes(boxes, overlay_enabled)
        except Exception as e:
            print(f"[overlay] Error: {e}")

        # No sleep — inference time is the natural rate limiter (~3-5 FPS on Pi 4)

    print("[overlay] Overlay thread stopped")


# ── Captioning Thread ─────────────────────────────────────────

def run_captioning(state, log: CaptionLog, config=None):
    """
    Detect-first caption flow with 1.5s presence window.
    See module docstring for full flow description.
    """
    global manual_trigger

    cfg               = config or {}
    confirm_window    = cfg.get("confirm_window",    5)
    confirm_hits      = cfg.get("confirm_hits",      3)
    min_motion_area   = cfg.get("min_motion_area",   2000)
    presence_duration = cfg.get("presence_duration", 1.5)
    presence_interval = cfg.get("presence_interval", 0.5)
    presence_min_hits = cfg.get("presence_min_hits", 2)

    net            = None
    last_run_ts    = 0.0
    busy           = False
    motion_history = deque(maxlen=confirm_window)

    print(
        f"[caption] Caption thread started — "
        f"confirm {confirm_hits}/{confirm_window} frames, "
        f"min area {min_motion_area}px², "
        f"presence {presence_duration}s"
    )

    while state.running:
        time.sleep(0.25)

        status      = state.get_status()
        now         = time.time()
        on_cooldown = (now - last_run_ts) < CAPTION_COOLDOWN

        motion_history.append(status["motion"])
        motion_hits = sum(motion_history)

        # ── Manual trigger — bypasses confirmation + presence window ──
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

        # ── Auto trigger — motion confirmation gate ───────────────────
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
                print(
                    f"[caption] Motion confirmed — "
                    f"{motion_hits}/{confirm_window} frames, "
                    f"area={status['motion_area']}px² — running detection"
                )

        if not fired_manual and not fired_auto:
            if not busy and not on_cooldown:
                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
            continue

        # ── Kick off detect-first + presence watch in worker thread ──
        busy  = True
        frame = state.get_frame()

        def _watch(frame_copy, trigger_source):
            """
            Full detect-first presence flow.
            Manual trigger skips presence window and logs immediately.
            Auto trigger requires object to persist for presence_duration.
            """
            nonlocal net, busy, last_run_ts

            try:
                # Load model if needed
                if net is None:
                    state.caption_status = "LOADING MODEL..."
                    net = _load_net()

                # ── Step 1: initial detection pass ───────────────────
                state.caption_status = "SCANNING..."
                initial_found = _interesting_labels(net, frame_copy)

                if not initial_found:
                    # Nothing interesting — drop silently, don't log
                    print("[caption] Detection pass — nothing interesting, dropping")
                    state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                    busy = False
                    return

                print(f"[caption] Detected {initial_found} — watching for {presence_duration}s")

                # ── Manual: log immediately, no presence window ───────
                if trigger_source == "MANUAL":
                    caption = _labels_to_caption(net, frame_copy)
                    caption = f"[manual] {caption}"
                    last_run_ts = time.time()
                    state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                    state.latest_caption = caption
                    log.append(caption, frame_copy)
                    busy = False
                    return

                # ── Auto: presence window ─────────────────────────────
                # Run detection every presence_interval seconds for
                # presence_duration total. Count how many passes confirm
                # at least one of the initially detected labels.
                state.caption_status = "WATCHING..."

                watch_start   = time.time()
                check_passes  = 0   # total checks run
                confirm_count = 0   # checks that confirmed an interesting object
                last_frame    = frame_copy  # keep most recent frame for thumbnail

                while (time.time() - watch_start) < presence_duration:
                    time.sleep(presence_interval)
                    check_passes += 1

                    current_frame = state.get_frame()
                    if current_frame is None:
                        continue

                    last_frame    = current_frame
                    current_found = _interesting_labels(net, current_frame)

                    # Accept if ANY interesting object still present
                    # (not just the originally detected one — it may have
                    #  moved or a second object joined the scene)
                    if current_found:
                        confirm_count += 1
                        print(
                            f"[caption] Presence check {check_passes}: "
                            f"{current_found} — {confirm_count} confirms"
                        )
                    else:
                        print(
                            f"[caption] Presence check {check_passes}: "
                            f"nothing — {confirm_count} confirms so far"
                        )

                # ── Consistency gate ──────────────────────────────────
                if confirm_count < presence_min_hits:
                    print(
                        f"[caption] Presence failed — "
                        f"{confirm_count}/{presence_min_hits} confirms needed, dropping"
                    )
                    state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                    busy = False
                    return

                # ── Passed — log it ───────────────────────────────────
                caption = _labels_to_caption(net, last_frame)
                last_run_ts = time.time()   # cooldown starts NOW, after watch
                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                state.latest_caption = caption
                log.append(caption, last_frame)
                print(
                    f"[caption] Logged after presence window "
                    f"({confirm_count}/{check_passes} confirms)"
                )

            except Exception as ex:
                print(f"[caption] Error: {ex}")
                state.caption_status = "ERROR"
                log.append(f"[error: {ex}]", frame_copy)
            finally:
                busy = False

        source = "MANUAL" if fired_manual else "AUTO"
        state.caption_status = f"SCANNING..."
        threading.Thread(target=_watch, args=(frame, source), daemon=True).start()

    print("[caption] Caption thread stopped")


# ── Detection helpers ─────────────────────────────────────────

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


def _interesting_labels(net, frame):
    """
    Returns a set of interesting label strings found in frame,
    empty set if nothing detected above confidence threshold.
    """
    boxes = _detect_boxes(net, frame)
    return {label for (_, _, _, _, label, _) in boxes}


def _labels_to_caption(net, frame):
    """Run detection and return a human-readable caption string."""
    boxes = _detect_boxes(net, frame)

    if not boxes:
        return "motion detected — no objects identified"

    # Collapse to highest confidence per label
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