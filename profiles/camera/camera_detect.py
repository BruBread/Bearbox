#!/usr/bin/env python3
"""
BearBox Camera — Motion Detection

Reads frames from the camera, runs frame-differencing motion detection,
annotates frames, and exposes results via DetectionState for all other
threads to read.

No inference happens here — frames are sent to the laptop for AI description.
"""

import cv2
import time
import threading


class DetectionState:
    """Shared state between detection, sender, stream, and display threads."""

    def __init__(self):
        self._lock           = threading.Lock()
        self.latest_frame    = None    # annotated frame (numpy BGR)
        self.motion          = False   # True if motion this frame
        self.motion_count    = 0       # total motion events since start
        self.motion_area     = 0       # total contour area this frame (px²)
        self.fps             = 0.0
        self.last_motion_ts  = None    # time.time() of last motion event
        self.running         = True    # set False to stop all threads

        # AI sender status — written by sender thread, read by display + stream
        # Values: "IDLE" | "SEARCHING..." | "SENDING..." | "COOLDOWN" |
        #         "NO CONNECTION" | "TIMEOUT" | "ERROR" | "AUTO OFF"
        self.ai_status          = "IDLE"
        self.latest_description = None   # last natural language result from laptop

    # ── Detection updates ──────────────────────────────────────

    def update(self, frame, motion, fps, motion_area=0):
        with self._lock:
            self.latest_frame = frame
            self.fps          = fps
            self.motion_area  = motion_area
            if motion and not self.motion:
                self.motion_count  += 1
                self.last_motion_ts = time.time()
            self.motion = motion

    def get_frame(self):
        """Return a copy of the latest annotated frame."""
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_stream_frame(self):
        """Return latest frame for the MJPEG stream."""
        with self._lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def get_status(self):
        with self._lock:
            return {
                "motion":              self.motion,
                "motion_count":        self.motion_count,
                "motion_area":         self.motion_area,
                "fps":                 round(self.fps, 1),
                "last_motion":         self.last_motion_ts,
                "ai_status":           self.ai_status,
                "latest_description":  self.latest_description,
            }


# ── Detection loop ─────────────────────────────────────────────

def run_detection(state: DetectionState, config: dict):
    """
    Main detection loop. Runs in its own daemon thread.

    config keys:
        camera_index    : int              — default 0
        resolution      : (w, h)           — default (640, 480)
        threshold       : int px²          — default 500
        detect_every    : int frames       — default 3
        blur_size       : int kernel size  — default 21
    """
    cam_idx      = config.get("camera_index",  0)
    res          = config.get("resolution",    (640, 480))
    threshold    = config.get("threshold",     500)
    detect_every = config.get("detect_every",  3)
    blur_size    = config.get("blur_size",     21)

    cap = cv2.VideoCapture(cam_idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  res[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res[1])
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print(f"[detect] ERROR: could not open camera {cam_idx}")
        state.running = False
        return

    print(f"[detect] Camera {cam_idx} opened at {res[0]}x{res[1]}")

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
            print("[detect] Frame read failed, retrying...")
            time.sleep(0.1)
            continue

        frame_idx  += 1
        fps_frames += 1

        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps        = fps_frames / elapsed
            fps_frames = 0
            fps_start  = time.time()

        if frame_idx % detect_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)

            if prev_gray is not None:
                diff    = cv2.absdiff(prev_gray, gray)
                thresh  = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                thresh  = cv2.dilate(thresh, None, iterations=2)
                cnts, _ = cv2.findContours(
                    thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                motion      = False
                motion_area = 0
                for c in cnts:
                    area = cv2.contourArea(c)
                    if area < threshold:
                        continue
                    motion       = True
                    motion_area += int(area)
                    x, y, w, h   = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

            prev_gray = gray

        _annotate(frame, motion, fps, state.motion_count)
        state.update(frame, motion, fps, motion_area)

    cap.release()
    print("[detect] Detection thread stopped")


def _annotate(frame, motion, fps, count):
    """Minimal HUD overlay drawn onto every frame."""
    h, w = frame.shape[:2]

    cv2.putText(
        frame, f"{fps:.1f} fps",
        (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
        0.5, (180, 180, 180), 1, cv2.LINE_AA
    )

    label = f"motion: {count}"
    lw    = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
    cv2.putText(
        frame, label,
        (w - lw - 8, 20), cv2.FONT_HERSHEY_SIMPLEX,
        0.5, (180, 180, 180), 1, cv2.LINE_AA
    )

    if motion:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 220), 3)
