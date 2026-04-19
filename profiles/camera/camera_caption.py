#!/usr/bin/env python3
"""
BearBox Camera — AI Motion Captioning

Watches DetectionState for rising-edge motion events.
On each new event (subject to cooldown), grabs the current frame,
runs moondream2 locally to generate a natural-language description,
and appends the result to CaptionLog.

Flood protection:
  - Rising-edge only (one trigger per motion event, not per frame)
  - Hard cooldown between captions (default 15s, applies to both auto + manual)
  - Single worker — if inference is running, new events are skipped
  - Lazy model load — moondream2 loads only on first trigger

Controls (set from camera_stream.py via this module's globals):
  auto_enabled   — bool, enables/disables automatic motion-triggered captioning
  manual_trigger — bool, set True to fire one manual capture regardless of auto state

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
from collections import deque

# ── Public control flags (written by camera_stream, read by run_captioning) ──
auto_enabled   = True   # toggle auto motion-triggered captioning
manual_trigger = False  # set True to fire one capture immediately

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
            "timestamp":  time.time(),
            "caption":    caption,
            "thumb_b64":  thumb_b64,
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

# Cooldown between caption jobs in seconds.
# Applies to BOTH automatic and manual triggers — prevents spam.
# Lower to 5.0 for demos/presentations.
CAPTION_COOLDOWN = 15.0

# moondream2 prompt — kept tight for surveillance context
_PROMPT = (
    "Describe in one short sentence what is happening in this image. "
    "Focus on people, animals, or objects that are moving."
)


def run_captioning(state, log: CaptionLog):
    """
    Main caption loop. Runs in its own daemon thread.
    state  — DetectionState instance
    log    — CaptionLog instance
    """
    global manual_trigger

    model        = None   # lazy load
    processor    = None
    last_count   = 0      # motion_count we last processed
    last_run_ts  = 0.0    # time.time() of last inference start
    busy         = False  # True while inference is running

    print("[caption] Caption thread started — waiting for trigger...")

    while state.running:
        time.sleep(0.25)  # polling interval — light on CPU

        status      = state.get_status()
        cur_count   = status["motion_count"]
        now         = time.time()
        on_cooldown = (now - last_run_ts) < CAPTION_COOLDOWN

        # ── Check for manual trigger ──────────────────────────
        fired_manual = False
        if manual_trigger:
            manual_trigger = False          # consume the flag immediately
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

        # Always sync last_count so stale events don't queue up
        last_count = cur_count

        # Neither trigger fired → update idle status and loop
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
            nonlocal model, processor, busy
            try:
                # ── Lazy model load ───────────────────────────
                if model is None:
                    print("[caption] Loading moondream2 — first trigger...")
                    state.caption_status = "LOADING MODEL..."
                    try:
                        import moondream as md
                        model = md.vl(model="moondream-2b-int8.mf")
                        processor = None
                        print("[caption] moondream2 loaded (moondream library)")
                    except Exception as e_md:
                        print(f"[caption] moondream lib failed ({e_md}), trying transformers...")
                        try:
                            from transformers import AutoModelForCausalLM, AutoTokenizer
                            _mdname = "vikhyatk/moondream2"
                            _rev    = "2025-01-09"
                            processor = AutoTokenizer.from_pretrained(
                                _mdname, revision=_rev, trust_remote_code=True
                            )
                            model = AutoModelForCausalLM.from_pretrained(
                                _mdname, revision=_rev,
                                trust_remote_code=True,
                                low_cpu_mem_usage=True,
                            )
                            model.eval()
                            print("[caption] moondream2 loaded (transformers)")
                        except Exception as e_tr:
                            print(f"[caption] ERROR: could not load moondream2: {e_tr}")
                            state.caption_status = "ERROR"
                            log.append("[model load failed]", frame_copy)
                            busy = False
                            return

                # ── Run inference ─────────────────────────────
                state.caption_status = "PROCESSING..."
                caption = _run_inference(model, processor, frame_copy)

                # tag manual captures in the log so they're identifiable
                if trigger_source == "MANUAL":
                    caption = f"[manual] {caption}"

                state.caption_status = "IDLE" if auto_enabled else "AUTO OFF"
                state.latest_caption = caption
                log.append(caption, frame_copy)

            except Exception as ex:
                print(f"[caption] Inference error: {ex}")
                state.caption_status = "ERROR"
                log.append(f"[error: {ex}]", frame_copy)
            finally:
                busy = False

        t = threading.Thread(
            target=_infer, args=(frame, source), daemon=True
        )
        t.start()

    print("[caption] Caption thread stopped")


def _run_inference(model, processor, frame):
    """
    Run moondream2 on a BGR numpy frame.
    Handles both the official moondream library and the transformers path.
    Returns a caption string.
    """
    from PIL import Image

    # BGR → RGB → PIL
    rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    # ── Official moondream library ────────────────────────────
    if processor is None:
        try:
            encoded = model.encode_image(pil_img)
            result  = model.query(encoded, _PROMPT)
            if isinstance(result, dict):
                return result.get("answer", str(result)).strip()
            return str(result).strip()
        except Exception as e:
            print(f"[caption] moondream lib query error: {e}")
            raise

    # ── Transformers path ─────────────────────────────────────
    try:
        answer = model.answer_question(
            model.encode_image(pil_img),
            _PROMPT,
            processor,
        )
        return str(answer).strip()
    except Exception as e:
        print(f"[caption] transformers query error: {e}")
        raise