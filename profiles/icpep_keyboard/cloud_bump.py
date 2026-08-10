#!/usr/bin/env python3
"""
BearBox — ICPEP Cloud Counter Bump

Fires a background request at the same Firebase Realtime Database the
TypeGrindr counter page (browser, /counters/parade) reads from, so a
physical ENTER press here bumps the same shared head-count shown there.

Non-blocking and silent on failure: the eye animation loop runs at 30fps
and must never stall on network latency, and a dropped/offline connection
just means this one press didn't reach the cloud — matches BearBox's
existing "degrade silently, come back on its own" philosophy (see
net_utils.has_internet()). The Pi's own screen never shows the number —
only eyes react locally; the count only ever appears in the browser.
"""

import threading
import requests

COUNTER_URL = (
    "https://typegrind-leaderboard-default-rtdb.asia-southeast1"
    ".firebasedatabase.app/counters/parade.json"
)
BUMP_TIMEOUT = 2.0  # seconds — short, this is fire-and-forget


def _do_bump():
    try:
        # {".sv": {"increment": 1}} is Firebase's atomic server-side +1 —
        # same mechanism the browser side uses (ServerValue.increment), so
        # simultaneous presses from the Pi and any open browser tab never
        # race or double-count each other.
        requests.patch(
            COUNTER_URL,
            json={
                "count": {".sv": {"increment": 1}},
                "updatedAt": {".sv": "timestamp"},
            },
            timeout=BUMP_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        print(f"[icpep] cloud counter bump failed (offline?): {e}")


def bump():
    """Fire-and-forget +1 to the shared parade counter. Never blocks the caller."""
    threading.Thread(target=_do_bump, daemon=True).start()
