#!/usr/bin/env python3
"""
BearBox Camera — Motion Detection

Reads frames from a shared source, runs frame-differencing
motion detection, annotates frames, and exposes results via
shared state for the display and Flask stream to read.

Usage:
    from camera_detect import DetectionState, run_detection
    state = DetectionState()
    thread = threading.Thread(target=run_detection, args=(state,), daemon=True)
    thread.start()
"""

import cv2
import time
import threading
import numpy as np


class DetectionState:
    """Shared state between detection, display, and stream threads."""

    def __init__(self):
        self._lock          = threading.Lock()
        self.latest_frame   = None   # annotated frame (numpy array, BGR)
        self.motion         = False  # True if motion detected this frame
        self.motion_count   = 0      # total motion events since start
        self.fps            = 0.0
        self.last_motion_ts = None   # time.time() of last motion event
        self.running        = True   # set False to stop the thread

    def update(self, frame, motion, fps):
        with self._lock:
            self.latest_frame = frame
            self.fps          = fps
            if motion and not self.motion:
                # rising edge — new motion event
                self.motion_count   += 1
                self.last_motion_ts  = time.time()
            self.motion = motion

    def get_frame(self):
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_status(self):
        with self._lock:
            return {
                "motion":       self.motion,
                "motion_count": self.motion_count,
                "fps":          round(self.fps, 1),
                "last_motion":  self.last_motion_ts,
            }


def run_detection(state: DetectionState, config: dict):
    """
    Main detection loop. Runs in its own thread.
    config keys:
        resolution  : (w, h) tuple          — default (640, 480)
        camera_index: int                   — default 0
        threshold   : int contour min area  — default 500
        detect_every: int frames to skip    — default 3
        blur_size   : gaussian kernel size  — default 21
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

    prev_gray  = None
    frame_idx  = 0
    motion     = False

    # FPS tracking
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

        # update FPS every second
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps        = fps_frames / elapsed
            fps_frames = 0
            fps_start  = time.time()

        # run detection every N frames
        if frame_idx % detect_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)

            if prev_gray is not None:
                diff    = cv2.absdiff(prev_gray, gray)
                thresh  = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                thresh  = cv2.dilate(thresh, None, iterations=2)
                cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)

                motion = False
                for c in cnts:
                    if cv2.contourArea(c) < threshold:
                        continue
                    motion = True
                    x, y, w, h = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x, y), (x + w, y + h),
                                  (0, 0, 255), 2)

            prev_gray = gray

        # always annotate with status
        _annotate(frame, motion, fps, state.motion_count)

        state.update(frame, motion, fps)

    cap.release()
    print("[camera] Detection thread stopped")


def _annotate(frame, motion, fps, count):
    """Draw minimal status overlay on the frame."""
    h, w = frame.shape[:2]

    # FPS — top left
    cv2.putText(frame, f"{fps:.1f} fps",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # motion count — top right
    label = f"motion: {count}"
    lw, _  = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
    cv2.putText(frame, label,
                (w - lw - 8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # red border when motion active
    if motion:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 220), 3)
