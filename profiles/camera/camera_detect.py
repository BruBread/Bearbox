#!/usr/bin/env python3
"""
BearBox Camera — Motion Detection

Reads frames from a shared source, runs frame-differencing
motion detection, annotates frames, and exposes results via
shared state for the display and Flask stream to read.

Changes v2:
  - DetectionState now tracks motion_area (total contour px²)
  - get_stream_frame() redraws cached overlay boxes at full camera FPS
    instead of waiting for inference to complete — no more lag
  - set_overlay_boxes() stores box list; draw happens inside get_stream_frame
  - overlay_frame field removed — boxes are the canonical overlay state now

Usage:
    from camera_detect import DetectionState, run_detection
    state = DetectionState()
    thread = threading.Thread(target=run_detection, args=(state,), daemon=True)
    thread.start()
"""

import cv2
import time
import threading


class DetectionState:
    """Shared state between detection, display, stream, and caption threads."""

    def __init__(self):
        self._lock           = threading.Lock()
        self.latest_frame    = None   # raw annotated frame (numpy array, BGR)
        self.motion          = False  # True if motion detected this frame
        self.motion_count    = 0      # total motion events since start
        self.motion_area     = 0      # total contour area this frame (px²)
        self.fps             = 0.0
        self.last_motion_ts  = None   # time.time() of last motion event
        self.running         = True   # set False to stop all threads

        # Caption pipeline status — written by caption thread, read by display + Flask
        # Values: "IDLE" | "MOTION DETECTED" | "PROCESSING..." | "COOLDOWN" | "ERROR" | "AUTO OFF"
        self.caption_status  = "IDLE"
        self.latest_caption  = None

        # Overlay box cache — inference results stored here, redrawn on every stream frame
        # Each entry: (x1, y1, x2, y2, label, confidence)
        self._overlay_boxes   = []
        self._overlay_enabled = False

    # ── Detection updates ─────────────────────────────────────

    def update(self, frame, motion, fps, motion_area=0):
        with self._lock:
            self.latest_frame = frame
            self.fps          = fps
            self.motion_area  = motion_area
            if motion and not self.motion:
                # rising edge — new motion event
                self.motion_count   += 1
                self.last_motion_ts  = time.time()
            self.motion = motion

    def get_frame(self):
        """Return the raw motion-annotated frame (used by caption thread)."""
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    # ── Overlay box cache ─────────────────────────────────────

    def set_overlay_boxes(self, boxes, enabled):
        """
        Called by overlay thread after each inference pass.
        boxes   : list of (x1, y1, x2, y2, label, confidence)
        enabled : current value of overlay_enabled flag
        Storing just the box list means get_stream_frame can redraw
        them onto every fresh camera frame at full FPS.
        """
        with self._lock:
            self._overlay_boxes   = boxes
            self._overlay_enabled = enabled

    def get_stream_frame(self):
        """
        Returns latest camera frame at full camera FPS.
        If overlay is enabled, cached detection boxes are redrawn on top.
        Never blocks on inference — always returns immediately.
        """
        with self._lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
            if self._overlay_enabled and self._overlay_boxes:
                _draw_boxes(frame, self._overlay_boxes)
        return frame

    def get_status(self):
        with self._lock:
            return {
                "motion":         self.motion,
                "motion_count":   self.motion_count,
                "motion_area":    self.motion_area,
                "fps":            round(self.fps, 1),
                "last_motion":    self.last_motion_ts,
                "caption_status": self.caption_status,
                "latest_caption": self.latest_caption,
            }


# ── Box drawing helper ────────────────────────────────────────
# Kept here so camera_detect owns the draw logic and camera_caption
# only needs to produce box tuples.

_COLORS = {
    "person":    (0,   200, 255),
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


def _draw_boxes(frame, boxes):
    """Draw cached detection boxes onto frame in-place."""
    for (x1, y1, x2, y2, label, conf) in boxes:
        color = _COLORS.get(label, _DEFAULT_COLOR)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        tag = f"{label} {int(conf * 100)}%"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        pill_y1 = max(y1 - th - 6, 0)
        pill_y2 = max(y1, th + 6)
        cv2.rectangle(frame, (x1, pill_y1), (x1 + tw + 6, pill_y2), color, -1)
        cv2.putText(frame, tag, (x1 + 3, pill_y2 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)


# ── Detection loop ────────────────────────────────────────────

def run_detection(state: DetectionState, config: dict):
    """
    Main detection loop. Runs in its own thread.
    config keys (all optional):
        resolution      : (w, h) tuple         — default (640, 480)
        camera_index    : int                  — default 0
        threshold       : int contour min area — default 500
        detect_every    : int frames to skip   — default 3
        blur_size       : gaussian kernel size — default 21
    """
    res          = config.get("resolution",   (640, 480))
    cam_idx      = config.get("camera_index", 0)
    threshold    = config.get("threshold",    500)
    detect_every = config.get("detect_every", 3)
    blur_size    = config.get("blur_size",    21)

    cap = cv2.VideoCapture(cam_idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  res[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res[1])
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print(f"[camera] ERROR: could not open camera {cam_idx}")
        state.running = False
        return

    print(f"[camera] Opened camera {cam_idx} at {res[0]}x{res[1]}")

    prev_gray   = None
    frame_idx   = 0
    motion      = False
    motion_area = 0

    fps_start  = time.time()
    fps_frames = 0
    fps        = 0.0

    while state.running:
        ok, frame = cap.read()
        if not ok:
            print("[camera] Frame read failed, retrying...")
            time.sleep(0.1)
            continue

        frame_idx  += 1
        fps_frames += 1

        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps        = fps_frames / elapsed
            fps_frames = 0
            fps_start  = time.time()

        # Run motion detection every N frames
        if frame_idx % detect_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)

            if prev_gray is not None:
                diff    = cv2.absdiff(prev_gray, gray)
                thresh  = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                thresh  = cv2.dilate(thresh, None, iterations=2)
                cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)

                motion      = False
                motion_area = 0
                for c in cnts:
                    area = cv2.contourArea(c)
                    if area < threshold:
                        continue
                    motion       = True
                    motion_area += int(area)
                    x, y, w, h   = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x, y), (x + w, y + h),
                                  (0, 0, 255), 2)

            prev_gray = gray

        _annotate(frame, motion, fps, state.motion_count)
        state.update(frame, motion, fps, motion_area)

    cap.release()
    print("[camera] Detection thread stopped")


def _annotate(frame, motion, fps, count):
    """Draw minimal status overlay on the frame."""
    h, w = frame.shape[:2]

    cv2.putText(frame, f"{fps:.1f} fps",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (180, 180, 180), 1, cv2.LINE_AA)

    label = f"motion: {count}"
    lw, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
    cv2.putText(frame, label,
                (w - lw - 8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (180, 180, 180), 1, cv2.LINE_AA)

    if motion:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 220), 3)
